# Workspace smoke tests

These tests change a shared registry and start/restart a workspace. Use a disposable
workspace and an installation where you are authorized to manage the registry.
They never run in pull-request CI. Run the complete procedure separately on
upstream Eclipse Che/Kubernetes and OpenShift Dev Spaces/OpenShift; success on one
is not proof of the other.

## Prerequisites

- Python 3.10+, `kubectl`, cluster credentials, and registry-management permissions.
- A Che/Dev Spaces version exposing the AI provider selector and registry API.
- Two published injector images with **different upstream OMP versions**, and the
  expected OMP versions for both. Build/push these before starting; see
  [injector](injector.md) and [releases](releases.md).
- Configure private-registry pull credentials in the workspace namespace using
  normal Kubernetes/OpenShift image-pull Secrets and service-account mechanisms.
  Do not put credentials in registry.json or injector images.
- An authenticated dashboard session. Set `CHE_TOKEN` to a short-lived bearer
  token accepted by the dashboard gateway. Do not record it in artifacts or shell
  history. `--registry-url` is the actual dashboard backend AI registry endpoint,
  normally `https://<che-host>/dashboard/api/ai-registry`; deployments with a
  different dashboard base path must use their endpoint.

The helper uses the current kubectl context. Check it before proceeding:

```sh
kubectl config current-context
kubectl get checlusters.org.eclipse.che -A
```

## Install, recognize, and create

Example values below refer to images you published, not pre-existing releases.
Set `IMAGE_A`, `OMP_A`, `IMAGE_B`, `OMP_B`, and `REGISTRY_URL` accordingly.
For upstream Che set `CHE_NAMESPACE=eclipse-che`; for Dev Spaces use
`CHE_NAMESPACE=openshift-devspaces` and add `--openshift` to verification calls.

Back up the shared ConfigMap before the test, without backing up unrelated
Secrets. Preview the merge first:

```sh
python3 scripts/registry.py install --namespace "$CHE_NAMESPACE" \
  --image "$IMAGE_A" --tag smoke-a --dry-run
python3 scripts/e2e.py prepare --che-namespace "$CHE_NAMESPACE" \
  --image "$IMAGE_A" --tag smoke-a --registry-url "$REGISTRY_URL"
```

`prepare` installs/merges OMP, calls the actual dashboard backend, and verifies
that it exposes both `oh-my-pi/omp` and the selected image. It saves the returned
registry. If backend refresh is delayed, wait and repeat the idempotent command.
A missing provider is a failure, not permission to inject a hand-written substitute.

In the dashboard, open **Create Workspace**, select **OMP** in the AI selector,
and create a disposable workspace with a Linux tools container and a writable
home directory. Record its DevWorkspace name, namespace, and tools container name.
The interactive step intentionally exercises the real dashboard's generated
workload rather than duplicating injection logic in a test fixture.

```sh
python3 scripts/e2e.py verify --image "$IMAGE_A" --omp-version "$OMP_A" \
  --workspace-namespace "$WORKSPACE_NAMESPACE" --workspace "$WORKSPACE" \
  --container tools --artifacts artifacts/initial
```

Verification waits for Running, checks the DevWorkspace image and the generated
pod's successfully completed injector, then runs the injected `omp --version`
and `omp --help` inside the selected container. In the dashboard terminal, also
run `command -v omp` and `omp --version` in a new shell to verify the dashboard's
PATH setup. Configure model authentication using OMP itself; no model call or
paid API key is needed for the smoke test.

## Restart

```sh
python3 scripts/e2e.py restart --image "$IMAGE_A" --omp-version "$OMP_A" \
  --workspace-namespace "$WORKSPACE_NAMESPACE" --workspace "$WORKSPACE" \
  --container tools --artifacts artifacts/restart
```

This stops the DevWorkspace, waits for Stopped, starts it, waits for Running, and
repeats verification. It does not change the workspace injection definition.

## Upgrade

```sh
python3 scripts/e2e.py upgrade --che-namespace "$CHE_NAMESPACE" \
  --image "$IMAGE_B" --tag smoke-b --registry-url "$REGISTRY_URL"
```

Stop the workspace and start it **through the Che dashboard**, allowing Che to
reconcile the changed registry before startup. A direct `kubectl` start bypasses
the dashboard reconciliation and cannot prove registry-driven upgrade behavior.
Select the new OMP version in workspace configuration if your Che version asks.
Do not edit the injector image manually: that would bypass the behavior under test.

```sh
python3 scripts/e2e.py verify --image "$IMAGE_B" --omp-version "$OMP_B" \
  --workspace-namespace "$WORKSPACE_NAMESPACE" --workspace "$WORKSPACE" \
  --container tools --artifacts artifacts/upgrade
```

The generated pod must use B, and OMP must report B's version, not A's cached
binary. Re-run the new-shell PATH check after upgrading.

## OpenShift-specific checks

Add `--openshift` to `verify` and `restart`. The script checks a restricted SCC,
a nonzero runtime UID, no privileged containers, and no explicit privilege
escalation. Successful injector completion also proves that configured cluster
image-pull credentials work. Do not grant `anyuid`, `privileged`, or SCC
exceptions to make the test pass. Check native addon extraction in a writable
home directory; see [injector runtime constraints](injector.md).

## Diagnostics and cleanup

On success or failure, workspace stages save the DevWorkspace, pods, namespace
events, and the last 200 log lines from all workspace/init containers. Logs may
contain user content: review before sharing. Never collect Secret objects.
Preserve the artifacts directory and record platform/version, image digests,
expected/observed OMP versions, SCC/UID, and stage result in your test report.

Delete the disposable workspace through the dashboard. If OMP was not installed
before this test, remove only its registry entries:

```sh
python3 scripts/registry.py uninstall --namespace "$CHE_NAMESPACE" --dry-run
python3 scripts/registry.py uninstall --namespace "$CHE_NAMESPACE"
```

If OMP existed before the test, restore its original image/tag using `install`
instead. Do not replace the whole shared ConfigMap from an old backup: unrelated
administrators may have changed other providers while the test ran.

## Implementation references

- [Che provider configuration](https://github.com/eclipse-che/che-docs/blob/main/modules/extend/pages/configuring-ai-providers.adoc)
- [Dashboard workload generation and upgrade reconciliation](https://github.com/eclipse-che/che-dashboard/blob/main/packages/dashboard-frontend/src/services/helpers/aiTools.ts)
- [Dashboard registry backend](https://github.com/eclipse-che/che-dashboard/blob/main/packages/dashboard-backend/src/routes/api/aiRegistry.ts)
