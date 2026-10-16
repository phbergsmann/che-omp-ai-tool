# OMP injector image

The injector uses Che's **`init`** pattern. The official Linux release is one
standalone executable, installed at `/usr/local/bin/omp`. Che copies that file to
`/injected-tools/bin/omp` and adds the destination to the workspace PATH. There
is no wrapper, second binary, npm install, Bun installation, or download at
workspace startup. Image environment variables are **not** copied by init.

## Red Hat Hardened Images

Both stages use the **Red Hat Hardened Images** catalog, not UBI:

- Fetch/build stage: `registry.access.redhat.com/hi/core-runtime:2.43-builder`.
- Shipped runtime: `registry.access.redhat.com/hi/core-runtime:2.43`.

Both references are pinned to multi-architecture manifest digests in
`Containerfile`. The runtime already supplies glibc, libgcc, libstdc++, and the
shell/copy utilities needed by Che's init command. No UBI/RHEL packages or
additional OS packages are installed. The builder variant's download/build
tools are not copied into the runtime; the runtime has no `dnf` or `microdnf`.
The image is not shell-free: Che explicitly invokes `/bin/sh`, `rm`, `mkdir`,
and `cp` during injection. Retaining those supplied tools is required.

Red Hat Hardened Images and UBI are distinct offerings; choosing a hardened base
does not make the upstream OMP/Bun binary Red Hat-built or Red Hat-certified.
The upstream binary remains subject to its own vulnerabilities and notices.
See the [Red Hat comparison](https://developers.redhat.com/articles/2026/06/29/red-hat-ubi-vs-red-hat-hardened-images-how-to-choose)
and [hardened image catalog](https://images.redhat.com/?search=core-runtime).

## Upstream evidence

These links are pinned to the version in `OMP_VERSION`:

- [Release builder](https://github.com/can1357/oh-my-pi/blob/v18.11.1/scripts/ci-release-build-binaries.ts)
  produces `omp-linux-x64` (Bun's baseline x64 target) and `omp-linux-arm64`.
- [Shared compiler](https://github.com/can1357/oh-my-pi/blob/v18.11.1/packages/coding-agent/scripts/compile-binary.ts)
  uses `Bun.build` with `compile`, embeds the native addon and documentation,
  and disables automatic loading of Bun/package configuration. The Bun runtime
  and JavaScript module graph are part of the executable.
- [Native embedder](https://github.com/can1357/oh-my-pi/blob/v18.11.1/packages/natives/scripts/embed-native.ts)
  includes compressed, version-stamped native addons for the target architecture.
- [Native loader](https://github.com/can1357/oh-my-pi/blob/v18.11.1/packages/natives/native/loader-state.js)
  decompresses those embedded bytes locally to a versioned native cache and
  loads the resulting `.node` library. This is extraction, not a network install.
- [Path helpers](https://github.com/can1357/oh-my-pi/blob/v18.11.1/packages/utils/src/dirs.ts)
  define user state and supported `PI_CODING_AGENT_DIR`, XDG, and native paths.
- [Che AI tool documentation](https://raw.githubusercontent.com/eclipse-che/che-docs/main/modules/extend/pages/configuring-ai-providers.adoc)
  describes the init binary injection contract.

A bundle is unnecessary: the native addon is already inside the executable.
This does **not** mean a static ELF executable or compatibility with arbitrary
Linux distributions. Use a matching-architecture glibc workspace with the
normal C/C++ runtime (glibc, libgcc, libstdc++), for example UBI 9. Alpine/musl
workspaces are not supported by these selected glibc assets.

Optional upstream features can require additional software or network access:
the compiler explicitly leaves `fastembed` and `onnxruntime-node` external, and
the [binary builder](https://github.com/can1357/oh-my-pi/blob/v18.11.1/packages/coding-agent/scripts/build-binary.ts)
documents an on-demand Transformers.js install for tiny-model features. Those
features are not preinstalled or promised as offline capabilities here. Model
requests naturally require a configured provider and connectivity. None is
needed for the startup smoke checks.

## Writable workspace state

The standalone executable must be able to write its native cache and user
configuration. In a normal Che workspace, leave `HOME` set to the workspace's
writable user home; defaults are `~/.omp/natives/<version>` and `~/.omp/agent`.
The native-cache filesystem must allow executable mappings (`dlopen`); a
`noexec` home/cache mount cannot load the native addon even though the CLI
itself is executable elsewhere. `/tmp` can remain `noexec`.

For a workspace with an unwritable home, explicitly configure **the workspace
container**, not the injector, with a writable HOME or supported absolute
`PI_NATIVES_DIR` and `PI_CODING_AGENT_DIR` paths. For example:

```yaml
env:
  - name: HOME
    value: /projects/omp-home
  - name: PI_NATIVES_DIR
    value: /projects/omp-home/.omp/natives
  - name: PI_CODING_AGENT_DIR
    value: /projects/omp-home/.omp/agent
```

Provision `/projects/omp-home` writable by the workspace UID and ensure its
volume permits executable mappings. A writable HOME is preferred because
upstream optional integrations can also use other home-relative locations.
`PI_NATIVES_DIR` is explicitly handled by `getNativesDir()` in the native loader;
it accepts an absolute path and recursively creates its version directory.
Do not assume XDG_CACHE_HOME alone moves that native cache: its XDG fallback
uses XDG_DATA_HOME only when the `omp` subdirectory already exists.

The injector itself defaults to non-root `10001:0`, with a group-0-writable
`/home/omp` and `/projects`, matching OpenShift arbitrary-UID conventions. It
does not need elevated capabilities or privilege escalation. No credentials,
provider settings, or user state are baked in. Its HOME default only applies
when running the injector image directly, not after Che copies the binary.

## Build and smoke

`OMP_VERSION` is the sole upstream pin. The Containerfile requires its build
argument rather than carrying a second version default:

```sh
CONTAINER_ENGINE=podman sh scripts/build-image.sh
CONTAINER_ENGINE=podman sh scripts/test-image.sh
```

Both helpers accept `IMAGE`; `CONTAINER_ENGINE=docker` selects Docker. Pass
additional build flags to the build helper, for example `--platform linux/arm64`
or `--platform linux/amd64`. Build each architecture on a native runner (or
with an appropriately configured engine). BuildKit supplies TARGETARCH;
otherwise a native build derives it from `uname -m`.

Build-time downloads use the tagged official GitHub release and verify the
chosen artifact against its exact entry in `SHA256SUMS.txt`. The manifest and
upstream MIT license, repository third-party notices, and native third-party
notices remain in the image under `/usr/share/omp` and `/usr/share/licenses/omp`.
Checksums from the same release ensure artifact integrity, not independent
publisher authentication. The upstream release and both hardened base manifest
digests are pinned. Rebuilding still depends on availability and immutability
of upstream release assets; byte-identical output is not claimed.

The smoke helper pulls its workspace base **before** offline execution. It
checks the canonical `omp/<version>` output, help, and arbitrary UID execution
with no network, all capabilities dropped, no-new-privileges and a read-only
root filesystem. It then copies only the executable through a volume and runs
it in an unrelated UBI workspace image with an empty writable HOME, a nonzero
arbitrary UID/GID, and no network. Command help also exercises native loading
and the test requires the extracted native cache to exist. Override
`WORKSPACE_IMAGE` to test an actual development image that satisfies the runtime
requirements. The script does not contact a model provider.
The UBI image is only an independent test workspace, not an injector build stage
or shipped base layer. This checks compatibility with existing Che development
images rather than forcing workspaces themselves to use the injector's base.

The default smoke UID is `12345`, unrelated to the image's configured UID and
within rootless Podman's subordinate-ID range. On a rootful engine,
`SMOKE_UID=1000750000` exercises an OpenShift-sized UID. A rootless engine cannot
map that UID unless its user namespace has a suitable mapping; this is an engine
constraint, not an injector permission requirement.

`SMOKE_PLATFORM=linux/amd64` (or `linux/arm64`) explicitly selects the injector
and workspace platform when testing a non-native image. Native runners are
preferred: the embedded Bun/JavaScriptCore runtime can fail under CPU emulation
even when the binary works on native hardware. Release validation therefore
uses a native runner for each architecture.

## Integration versus upstream metadata

`ghcr.io/phbergsmann/che-omp-ai-tool:v0.1.0` is the integration image version;
it is independent of the OMP version. `INTEGRATION_VERSION` populates the OCI
version label; `VCS_REF` supplies this repository's revision (default `unknown`
for a local build). `io.github.phbergsmann.omp.version` records the upstream tag.
The source label identifies this integration repository, while the separate
OMP source label identifies `can1357/oh-my-pi`. The license label records MIT
plus upstream third-party terms; consult the included notices for those terms.
