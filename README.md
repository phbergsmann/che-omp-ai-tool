# OMP for Eclipse Che and OpenShift Dev Spaces

A standalone integration that injects the [Oh My Pi (`omp`) coding agent](https://github.com/can1357/oh-my-pi)
into Che workspaces. No Autocode dependency, model credentials, or workspace-time
package installation. Model configuration remains OMP's responsibility.

Both build and runtime stages use digest-pinned **Red Hat Hardened Images**
(`hi/core-runtime`), not UBI. The injector contains an upstream standalone OMP
executable; that binary is not Red Hat-built or certified. The registry uses
`oh-my-pi/omp`, `binary: omp`, `pattern: init`, and explicitly supports x86_64 and
arm64. OMP is not selected by default. See [image design](docs/injector.md) for
native-library and writable-home requirements.

## Install

Release tags and image versions follow OMP: `OMP_VERSION` set to `v18.11.1`
means release and image tag `v18.11.1`. The registry template derives its defaults
from that file; use an image you built or a published release. The earlier
`v0.1.0` release remains historical and is not rewritten.

```sh
python3 scripts/registry.py validate
python3 scripts/registry.py install --namespace eclipse-che --dry-run
python3 scripts/registry.py install --namespace eclipse-che
```

For Dev Spaces use `--namespace openshift-devspaces`. Explicit namespaces are
supported. Prefer a published `@sha256:...` digest for reproducibility. Private
GHCR images require normal cluster image-pull credentials, configured separately.
Installation discovers the shared registry by labels, preserves foreign entries,
and refuses ambiguous discovery. See [registry operations](docs/registry.md).

```sh
python3 scripts/registry.py uninstall --namespace eclipse-che --dry-run
python3 scripts/registry.py uninstall --namespace eclipse-che
```

Select OMP in the dashboard when creating a workspace. Run `omp --version` in its
terminal, then configure models/authentication using OMP's normal configuration.

## Development

Layout: `Containerfile`, `registry/`, `scripts/`, `test/`, `docs/`, and
`.github/workflows/`. Python tooling uses only the standard library (Python 3.10+).

```sh
CONTAINER_ENGINE=podman bash scripts/check.sh
CONTAINER_ENGINE=podman bash scripts/build-image.sh
CONTAINER_ENGINE=podman bash scripts/test-image.sh
```

Install the lint tools/versions listed in the CI workflow before running the
static checks locally. Container verification needs a running Docker or Podman
engine. `OMP_VERSION` is the canonical build, registry, and release version.
Release tags must match it exactly; OCI revision metadata identifies the
integration's source commit.

Pull requests run static checks before one native-architecture image build/test.
They do not run QEMU, multi-architecture publishing, supply-chain release jobs,
or cluster E2E. [Release automation](docs/releases.md) builds both architectures,
produces SBOM/provenance, signs images, and publishes digest-pinned registry
artifacts. The scheduled/manual [Renovate workflow](docs/renovate.md) proposes
upstream updates without automatic merging. Configure `RENOVATE_APP_CLIENT_ID`
and `RENOVATE_APP_PRIVATE_KEY` as repository Actions secrets; the workflow
generates a fresh, repository-scoped GitHub App token for each run.

[Manual E2E procedures](docs/e2e.md) cover actual dashboard selection, injection,
restart, upgrade, restricted OpenShift security, and diagnostic capture. Run
these separately against Che and Dev Spaces; local image tests are not a claim
of live-workspace compatibility.
