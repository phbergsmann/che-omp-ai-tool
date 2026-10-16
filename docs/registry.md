# Che AI tool registry

The canonical source template is [`registry/registry.json`](../registry/registry.json).
It is valid JSON, but its `${OMP_VERSION}` markers must be rendered before
deployment; do not install the committed JSON directly. Rendering substitutes
only that known marker using [`OMP_VERSION`](../OMP_VERSION), never arbitrary
environment variables. It uses the current [Che AI provider schema](https://raw.githubusercontent.com/eclipse-che/che-docs/main/modules/extend/pages/configuring-ai-providers.adoc):
`providers`, `tools`, and `defaultAiProviders`. The same schema and discovery labels
apply to Eclipse Che and Red Hat OpenShift Dev Spaces.

## Identity and injection contract

`oh-my-pi/omp` is the reserved provider identity owned by this repository. The
installer replaces that provider and **all tool entries whose `providerId` is
`oh-my-pi/omp`**, regardless of their previous tag. Uninstall removes exactly those
entries. Do not assign this identity to independently managed integrations or
variants: entries with the same identity cannot be distinguished as foreign.
Other provider IDs, including tools named `omp` under another provider ID, remain
untouched. Tags identify image variants in Che's version picker, not model
backends. Installing a new tag replaces this integration's previous variants.

The binary is `omp`, the injection pattern is `init`, and supported node
architectures are explicitly `x86_64` and `arm64`. The injector copies its single
binary into `/injected-tools/bin`; no companion wrapper/runtime file is required.
The default image and Che tool tag derive from `OMP_VERSION`: currently
`ghcr.io/phbergsmann/che-omp-ai-tool:v18.11.1` and `v18.11.1`. The image version
matches upstream OMP; there is no separate integration release version.
`org.opencontainers.image.revision` identifies the integration's Git revision.
Use an image digest for immutable deployments rather than a moving alias.

OMP is not selected by default (`defaultAiProviders` is empty in the canonical
entry). There is no `envVarName`, backend key, or model credential in this registry
entry. Configure models, endpoints, and credentials through OMP's own settings in
the workspace; OpenAI, Anthropic, vLLM, and other backends are not separate Che
providers for this integration.

## Logo and Community metadata

The provider uses the upstream Oh My Pi collaboration application's
[square SVG favicon](https://github.com/can1357/oh-my-pi/blob/7cc912940b107eb2d771b0d106c640a8eddc9edf/packages/collab-web/public/favicon.svg),
pinned to commit `7cc912940b107eb2d771b0d106c640a8eddc9edf` (`v18.11.1`).
Its public `raw.githubusercontent.com` URL requires no authentication. The
gradient pi mark has its own dark rounded background, unlike the upstream
white-on-transparent header icon; it is intended to remain visible at the
dashboard's 20×20 icon size in both themes, including the dashboard's light
icon background in dark mode. This is OMP branding, not a model-provider logo.

The upstream repository distributes the asset under its
[MIT license](https://github.com/can1357/oh-my-pi/blob/7cc912940b107eb2d771b0d106c640a8eddc9edf/LICENSE):
copyright 2025 Mario Zechner, 2025–2026 Can Bölük, and 2026 Stencil Labs, Inc.
The asset is linked unchanged rather than copied into this private repository.
This usage does not imply upstream, Red Hat, or model-vendor support.

`tags: ["Community"]` describes maintenance of this Che integration only.
The provider remains `oh-my-pi/omp`, named `Oh My Pi`, published by `oh-my-pi`.
Do not replace it with `Tech-Preview` merely to obtain a visible badge.

**Visible Community badge pending upstream support.** OpenShift Dev Spaces
`3.30.2`, with dashboard image
`registry.redhat.io/devspaces/dashboard-rhel9@sha256:e5ce2b3dbfbf9f41883fc3291f6f11f937f8238238c9aa1b20b64d5bbb000600`,
filters AI card tags to the exact string `Tech-Preview`. This was verified in
its deployed `client.ef2c2550.js`; valid Community metadata is therefore not
displayed as a badge in that version. The dependency is
[eclipse-che/che#23997](https://github.com/eclipse-che/che/issues/23997), which
requests Community support while preserving Tech-Preview behavior. A dashboard
release containing that enhancement is required for a visible Community badge.
The logo can be deployed independently without replacing the dashboard.

Rendering, installation, and future release registry assets retain the icon and
tags. Existing immutable image tags and published release assets are not changed.
To update a current installation, use the current registry CLI with the **same**
image digest and tool tag already installed:

```sh
python3 scripts/registry.py install --namespace openshift-devspaces \
  --image "$CURRENT_IMAGE_DIGEST_REFERENCE" --tag "$CURRENT_TOOL_TAG" --dry-run
python3 scripts/registry.py install --namespace openshift-devspaces \
  --image "$CURRENT_IMAGE_DIGEST_REFERENCE" --tag "$CURRENT_TOOL_TAG"
```

Refresh the real provider selector and check both dashboard themes. The image
must load at 20×20 without being hidden by the card's image-error handler;
browser network/CSP rules must permit its public host. Community should be
visible only on a supporting dashboard; the metadata alone is not proof.

Manual verification on 2026-10-16 used the live deployed selector and real Che
APIs through an authenticated loopback transport, not mocked UI/API responses.
The unchanged SVG loaded anonymously and was visibly legible at computed
20×20 sizing in both light and dark themes, including the dark theme's
`rgb(242, 242, 242)` icon background. The image was not hidden; no Community
badge rendered, consistent with the deployed filter. Screenshots are recorded in
[issue #11](https://github.com/phbergsmann/che-omp-ai-tool/issues/11).

## Commands

Only Python 3's standard library is required for local validation and rendering:

```sh
python3 scripts/registry.py validate
python3 scripts/registry.py render --image registry.example.com/team/omp:dev > /tmp/omp-registry.json
python3 scripts/registry.py validate /tmp/omp-registry.json
python3 scripts/registry.py render --image registry.example.com/team/omp:dev --tag dev
```

Default `validate` renders and validates the canonical template. An explicit path
validates the supplied JSON as-is, without template expansion.
Image references require an explicit tag or a `sha256` digest. `--tag` controls the
Che tool tag independently of the image tag. Omit it to use `OMP_VERSION`.

Install requires an authenticated `kubectl` context with ConfigMap list/create/update
permissions in the **Che installation namespace**, not a developer workspace
namespace. Select `eclipse-che`, `openshift-devspaces`, or your actual custom
installation namespace explicitly:

```sh
python3 scripts/registry.py install --namespace eclipse-che --dry-run
python3 scripts/registry.py install --namespace eclipse-che
python3 scripts/registry.py install --namespace openshift-devspaces \
  --image registry.example.com/team/omp:dev --tag dev --dry-run
python3 scripts/registry.py install --namespace openshift-devspaces \
  --image registry.example.com/team/omp@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --tag production
```

Use `--kubectl oc` on install/uninstall to use the OpenShift CLI, or provide an
executable path. A dry run still reads the cluster but never writes: stdout is
the resulting JSON ConfigMap, including unrelated entries and metadata.
Rendering alone is entirely offline. Images in a private registry need pull
credentials made available to workspace init containers according to your Che or
Dev Spaces installation's image pull secret configuration. Registry installation
does not create secrets or embed registry credentials. Ensure your image supports
both declared architectures and that cluster nodes can pull it.

## Safe shared-registry updates

Discovery searches ConfigMaps in the selected namespace with **both** labels:

```text
app.kubernetes.io/component=ai-tool-registry
app.kubernetes.io/part-of=che.eclipse.org
```

No match creates `ai-tool-registry`. One match updates that object, even if its
name differs. Multiple matches fail explicitly; resolve the cluster ambiguity
rather than selecting an arbitrary registry. A same-name ConfigMap without the
labels is never adopted or overwritten: the Kubernetes create operation fails.

The merge preserves foreign provider/tool objects, their order, registry extension
fields, `defaultAiProviders`, ConfigMap metadata, unrelated data keys, and binary
data. A ConfigMap without `registry.json` starts an empty registry; an existing
malformed JSON value, missing schema arrays, duplicate JSON keys/provider IDs,
or dangling tool-provider reference is rejected without a write. Foreign tools
are not restricted to OMP's binary, architectures, or injection pattern. OMP
entries are checked strictly against this integration's contract.

Updates use `kubectl replace` with the discovered `resourceVersion`; a concurrent
modification fails rather than overwriting another administrator's update. New
objects use `kubectl create`. There is no blind apply, force replacement, or
automatic conflict retry. Read the diagnostic and rerun to discover and merge the
latest state. Repeated installs with the same inputs produce the same registry.

```sh
python3 scripts/registry.py uninstall --namespace eclipse-che --dry-run
python3 scripts/registry.py uninstall --namespace eclipse-che
```

Uninstall leaves the ConfigMap and all foreign entries intact; an absent registry
is a successful no-op. Defaults are preserved verbatim, including any explicit
administrator selection of OMP. If you selected OMP as a default manually, remove
that selection separately when uninstalling. Existing workspace files and model
credentials are not deleted by registry uninstall.

## Automated checks

Run the standard-library tests from the repository root:

```sh
python3 -m unittest discover -s test -p 'test_registry.py' -v
```

Tests cover version-file-driven defaults, canonical template rendering, explicit
file validation, discovery, creation, empty registries, foreign-data preservation,
idempotence, upgrades, uninstall, malformed registries, image overrides, strict
OMP validation, dry runs, optimistic concurrency, and error propagation without
cluster writes.
