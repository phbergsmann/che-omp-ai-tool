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

Use an image you have built/published, or a release image once a release has been
published. The committed registry describes integration `v0.1.0`; committing that
reference does not itself publish a GHCR image.

```sh
python3 scripts/registry.py validate
python3 scripts/registry.py install --namespace eclipse-che \
  --image ghcr.io/phbergsmann/che-omp-ai-tool:v0.1.0 --dry-run
python3 scripts/registry.py install --namespace eclipse-che \
  --image ghcr.io/phbergsmann/che-omp-ai-tool:v0.1.0
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
engine. `OMP_VERSION` is the single upstream-version source. Integration releases
have a separate version, selected by the repository release tag.

Pull requests run static checks before one native-architecture image build/test.
They do not run QEMU, multi-architecture publishing, supply-chain release jobs,
or cluster E2E. [Release automation](docs/releases.md) builds both architectures,
produces SBOM/provenance, signs images, and publishes digest-pinned registry
artifacts. Renovate proposes upstream release updates without automatic merging.

[Manual E2E procedures](docs/e2e.md) cover actual dashboard selection, injection,
restart, upgrade, restricted OpenShift security, and diagnostic capture. Run
these separately against Che and Dev Spaces; local image tests are not a claim
of live-workspace compatibility.
