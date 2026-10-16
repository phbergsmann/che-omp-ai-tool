#!/usr/bin/env python3
"""Manual-cluster smoke stages; never creates a substitute for dashboard injection."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, check=True):
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"{' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def kubectl(args, *command, check=True):
    return run([args.kubectl, '--request-timeout=30s', '-n', args.workspace_namespace,
                *command], check=check)


def collect(args):
    """Retain diagnostic workload state on success and failure; no Secrets."""
    directory = Path(args.artifacts)
    directory.mkdir(parents=True, exist_ok=True)
    for name, command in {
        'workspace.json': ['get', 'devworkspace', args.workspace, '-o', 'json'],
        'pods.json': ['get', 'pods', '-l', f'controller.devfile.io/devworkspace_name={args.workspace}', '-o', 'json'],
        'events.txt': ['get', 'events', '--sort-by=.lastTimestamp'],
    }.items():
        (directory / name).write_text(kubectl(args, *command, check=False))
    pods = json.loads((directory / 'pods.json').read_text() or '{"items": []}')
    for pod in pods.get('items', []):
        name = pod['metadata']['name']
        for container in pod['spec'].get('initContainers', []) + pod['spec'].get('containers', []):
            container_name = container['name']
            (directory / f'{name}-{container_name}.log').write_text(
                kubectl(args, 'logs', name, '-c', container_name, '--tail=200', check=False))


def registry(args):
    command = [sys.executable, str(ROOT / 'scripts/registry.py'), 'install',
               '--namespace', args.che_namespace, '--image', args.image, '--tag', args.tag,
               '--kubectl', args.kubectl]
    print(run(command), end='')


def backend(args):
    token = os.environ.get('CHE_TOKEN')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    request = urllib.request.Request(args.registry_url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if not any(p.get('id') == 'oh-my-pi/omp' for p in data['providers']):
        raise RuntimeError('Dashboard backend does not expose oh-my-pi/omp')
    if not any(t.get('providerId') == 'oh-my-pi/omp' and t.get('injectorImage') == args.image
               for t in data['tools']):
        raise RuntimeError('Dashboard backend does not expose the requested injector image')
    directory = Path(args.artifacts)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'backend-registry.json').write_text(json.dumps(data, indent=2) + '\n')
    print('Dashboard backend recognizes the OMP provider and image')


def wait_phase(args, expected):
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        workspace = json.loads(kubectl(args, 'get', 'devworkspace', args.workspace, '-o', 'json'))
        phase = workspace.get('status', {}).get('phase')
        if phase == expected:
            return workspace
        if phase == 'Failed' and expected != 'Stopped':
            raise RuntimeError('Workspace startup failed; inspect preserved artifacts')
        time.sleep(3)
    raise RuntimeError(f'Timed out waiting for workspace phase {expected}')


def verify(args):
    workspace = wait_phase(args, 'Running')
    components = workspace['spec']['template']['components']
    if not any(c.get('container', {}).get('image') == args.image for c in components):
        raise RuntimeError('DevWorkspace does not contain the selected injector image')
    pods = json.loads(kubectl(args, 'get', 'pods', '-l',
                            f'controller.devfile.io/devworkspace_name={args.workspace}', '-o', 'json'))['items']
    running = [p for p in pods if p.get('status', {}).get('phase') == 'Running'
               and not p['metadata'].get('deletionTimestamp')]
    if len(running) != 1:
        raise RuntimeError(f'Expected one running workspace pod, found {len(running)}')
    pod = running[0]
    injectors = [c for c in pod['spec'].get('initContainers', []) if c.get('image') == args.image]
    if not injectors:
        raise RuntimeError('Generated workload has no init container with the selected image')
    statuses = {c['name']: c for c in pod.get('status', {}).get('initContainerStatuses', [])}
    for injector in injectors:
        status = statuses.get(injector['name'], {})
        if status.get('state', {}).get('terminated', {}).get('exitCode') != 0:
            raise RuntimeError('OMP injector has not completed successfully')
    name = pod['metadata']['name']
    output = kubectl(args, 'exec', name, '-c', args.container, '--',
                     '/injected-tools/bin/omp', '--version').strip()
    if output != f"omp/{args.omp_version.removeprefix('v')}":
        raise RuntimeError(f'Version mismatch: expected {args.omp_version}, got {output!r}')
    help_text = kubectl(args, 'exec', name, '-c', args.container, '--',
                        '/injected-tools/bin/omp', '--help')
    if 'omp' not in help_text.lower():
        raise RuntimeError('Unexpected omp --help output')
    identity = kubectl(args, 'exec', name, '-c', args.container, '--', 'id')
    if args.openshift:
        scc = pod['metadata'].get('annotations', {}).get('openshift.io/scc', '')
        if scc not in ('restricted', 'restricted-v2', 'restricted-v3'):
            raise RuntimeError(f'Expected restricted OpenShift SCC, got {scc!r}')
        uid = kubectl(args, 'exec', name, '-c', args.container, '--', 'id', '-u').strip()
        if not uid.isdigit() or int(uid) == 0:
            raise RuntimeError('Expected an arbitrary non-root OpenShift UID')
        for container in pod['spec'].get('initContainers', []) + pod['spec']['containers']:
            security = container.get('securityContext', {})
            if security.get('privileged') or security.get('allowPrivilegeEscalation'):
                raise RuntimeError('Generated workload requests elevated privileges')
        print(f'OpenShift SCC: {scc}; UID: {uid}')
    print(f'{name}/{args.container}: omp {output}; {identity.strip()}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'verify', 'restart', 'upgrade'])
    parser.add_argument('--che-namespace', default='eclipse-che')
    parser.add_argument('--image', required=True)
    parser.add_argument('--tag')
    parser.add_argument('--omp-version', default=(ROOT / 'OMP_VERSION').read_text().strip())
    parser.add_argument('--registry-url', help='Authenticated dashboard /dashboard/api/ai-registry URL')
    parser.add_argument('--workspace-namespace')
    parser.add_argument('--workspace')
    parser.add_argument('--container', default='tools')
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--artifacts', default='artifacts/e2e')
    parser.add_argument('--openshift', action='store_true')
    args = parser.parse_args()
    if args.tag is None:
        args.tag = args.omp_version
    if args.stage in ('prepare', 'upgrade') and not args.registry_url:
        parser.error('--registry-url is required for backend recognition verification')
    if args.stage in ('verify', 'restart') and not (args.workspace_namespace and args.workspace):
        parser.error('--workspace-namespace and --workspace are required')
    try:
        if args.stage in ('prepare', 'upgrade'):
            registry(args)
            backend(args)
            print('Use the dashboard to select OMP and create/start the workspace; then run verify.')
        else:
            if args.stage == 'restart':
                kubectl(args, 'patch', 'devworkspace', args.workspace, '--type=merge',
                        '-p', '{"spec":{"started":false}}')
                wait_phase(args, 'Stopped')
                kubectl(args, 'patch', 'devworkspace', args.workspace, '--type=merge',
                        '-p', '{"spec":{"started":true}}')
            verify(args)
    except (RuntimeError, ValueError, OSError) as error:
        print(f'e2e: {error}', file=sys.stderr)
        return 1
    finally:
        if args.workspace_namespace and args.workspace:
            try:
                collect(args)
            except (RuntimeError, ValueError, OSError) as error:
                print(f'Artifact collection failed: {error}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
