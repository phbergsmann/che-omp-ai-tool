# Che AI tool registry

The canonical definition is [`registry/registry.json`](../registry/registry.json).
It uses the current [Che AI provider schema](https://raw.githubusercontent.com/eclipse-che/che-docs/main/modules/extend/pages/configuring-ai-providers.adoc):
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
The default image is `ghcr.io/phbergsmann/che-omp-ai-tool:v0.1.0`. Its integration
release tag is distinct from upstream OMP's version in `OMP_VERSION`.

OMP is not selected by default (`defaultAiProviders` is empty in the canonical
entry). There is no `envVarName`, backend key, or model credential in this registry
entry. Configure models, endpoints, and credentials through OMP's own settings in
the workspace; OpenAI, Anthropic, vLLM, and other backends are not separate Che
providers for this integration.

## Commands

Only Python 3's standard library is required for local validation and rendering:

```sh
python3 scripts/registry.py validate
python3 scripts/registry.py validate registry/registry.json
python3 scripts/registry.py render --image registry.example.com/team/omp:dev --tag dev
```

Image references require an explicit tag or a `sha256` digest. `--tag` controls the
Che tool tag independently of the image tag. Omit it to retain `v0.1.0`.

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

Tests cover discovery, creation, empty registries, foreign-data preservation,
idempotence, upgrades, uninstall, malformed registries, image overrides, strict
OMP validation, dry runs, optimistic concurrency, and error propagation without
cluster writes.
