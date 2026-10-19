# OMP for Eclipse Che and OpenShift Dev Spaces

Run the [Oh My Pi (`omp`) coding agent](https://github.com/can1357/oh-my-pi)
in Eclipse Che and Red Hat OpenShift Dev Spaces workspaces.

The integration provides a container image and an AI tool registry entry. Che
copies the standalone OMP executable into the workspace at startup, without
installing packages in the workspace. Users select OMP in the dashboard and
configure model providers and authentication through OMP.

## Features

- Supports Linux x86_64 and ARM64 workspaces.
- Uses digest-pinned Red Hat Hardened Images for the injector build and runtime.
- Supports non-root execution and OpenShift's arbitrary user IDs.
- Installs, upgrades, and removes the OMP registry entry while preserving other
  providers and administrator defaults.
- Publishes versioned multi-architecture images and digest-pinned registry assets.

The OMP executable comes from upstream releases; it is not Red Hat-built or
certified. See [image design and runtime requirements](docs/injector.md) for
workspace compatibility, native libraries, and writable-home requirements.

## Installation

Use a published image from [Releases](https://github.com/phbergsmann/che-omp-ai-tool/releases)
or build the image locally. Release tags and image versions match the upstream
OMP version recorded in `OMP_VERSION`.

The registry commands require Python 3.10+ and an authenticated `kubectl` context
with permission to manage ConfigMaps in the Che installation namespace.

Preview and install the registry entry:

```sh
python3 scripts/registry.py validate
python3 scripts/registry.py install --namespace eclipse-che --dry-run
python3 scripts/registry.py install --namespace eclipse-che
```

For OpenShift Dev Spaces, use `--namespace openshift-devspaces`. Use your actual
installation namespace if it differs. The installer discovers the shared registry
by labels and refuses ambiguous matches.

For a reproducible deployment, pass a published image digest with
`--image ghcr.io/phbergsmann/che-omp-ai-tool@sha256:<digest>`. Private images
require cluster image-pull credentials configured separately.

See [registry operations](docs/registry.md) for image overrides, upgrades,
permissions, and troubleshooting.

## Usage

1. Select **Oh My Pi** in the dashboard's AI provider selector when creating or
   configuring a workspace.
2. Start the workspace and run `omp --version` in its terminal.
3. Configure model providers and authentication using
   [OMP's configuration guidance](https://github.com/can1357/oh-my-pi).

To remove the registry entry:

```sh
python3 scripts/registry.py uninstall --namespace eclipse-che --dry-run
python3 scripts/registry.py uninstall --namespace eclipse-che
```

Removing the registry entry does not delete workspace files or model credentials.

## Development

The repository contains the injector `Containerfile`, registry template,
Python and shell tooling, tests, documentation, and GitHub Actions workflows.
Python tooling uses the standard library.

Install the lint tools and versions listed in the
[CI workflow](.github/workflows/ci.yml). Image builds and smoke tests require a
running Docker or Podman engine.

```sh
CONTAINER_ENGINE=podman bash scripts/check.sh
CONTAINER_ENGINE=podman bash scripts/build-image.sh
CONTAINER_ENGINE=podman bash scripts/test-image.sh
```

Pull requests run static validation before a native image build and smoke test.
Changes to `OMP_VERSION` on `main` automatically tag the commit and start the
multi-architecture release pipeline, including scanning, signing, and registry
asset publication. Existing release-environment approval rules apply.

- [Releases and publishing](docs/releases.md)
- [Dependency update automation](docs/renovate.md)
- [Che and OpenShift workspace smoke tests](docs/e2e.md)

Cluster smoke tests run separately from normal PR validation. Local image tests
do not replace verification in a running Che or Dev Spaces workspace.
