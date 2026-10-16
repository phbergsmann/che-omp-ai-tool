# Releases and upstream updates

## Versions

Integration tags such as `v0.1.0` version this repository, not OMP.
`OMP_VERSION` is the sole upstream dependency version source, initially
`v18.11.1`. Container builds read that file; release builds pass its value
explicitly. OCI labels expose the integration version, source revision and
embedded OMP version.

Renovate must be enabled for this repository (install/authorize the Renovate
GitHub App, including access to this private repository). `renovate.json` uses
the GitHub releases datasource for `can1357/oh-my-pi`, not page scraping.
Its update PRs identify both old and new OMP versions and change the canonical
version file. No OMP upgrade is automatically merged. Review compatibility,
including major upgrades, before merging. Updates use the ordinary CI path:
static validation, registry validation, one native image build and smoke tests
including `omp --version`. They cannot publish or run cluster E2E.

## Local quality gates

Install Python 3.12, Node/npm, a running Docker-compatible container engine,
and `python3 -m pip install yamllint==1.35.1`. Then run:

```sh
sh scripts/check.sh
sh scripts/build-image.sh
sh scripts/test-image.sh
```

Set `CONTAINER_ENGINE=podman` for each command to use Podman. The static checker
runs stdlib unit tests, registry validation, JSON parsing, ShellCheck 0.10.0,
Hadolint 2.12.0, yamllint 1.35.1 and markdownlint-cli2 0.17.2. The container
linters and pinned npm package require network access on first use. CI pins
Actions to commit SHAs and Python to 3.12.9; runner OS updates and vulnerability
databases intentionally remain current. No local check needs a cluster.

CI runs inexpensive checks before at most one native image build. Documentation
and unrelated configuration-only PRs skip the build through an input-path filter;
static checks still run. Pull requests never run QEMU, multiarch publishing,
signing, release scans or cluster E2E. There are no repository-specific secrets
committed to the configuration.

## Publishing

Configure the GitHub `release` environment with appropriate required reviewers
and restrict who can create `v*` tags. The workflow needs repository Actions
permissions to write packages/releases and request OIDC tokens. For private
packages, grant this repository Actions access to the package in GHCR settings.
The workflow authenticates pulls, pushes and scans with `GITHUB_TOKEN`; no
long-lived registry credential is needed.

Create and push an annotated integration release tag pointing at reviewed code:

```sh
git tag -a v0.1.0 -m 'Integration v0.1.0'
git push origin v0.1.0
```

Alternatively, run the Release workflow manually **from `main`**, supplying an
already existing integration tag. Publication only runs for tag pushes or this
trusted manual context. Version validation accepts stable `vX.Y.Z` and SemVer
prereleases such as `v1.0.0-rc.1`; build metadata is deliberately unsupported
because OCI tags cannot contain `+`.

Releases serialize globally so different version lines cannot race promotion.
The authenticated GHCR API is paginated and checked before building: an existing
full-version manifest is an error, never overwritten. Do not publish these
image tags outside this workflow, which would bypass its serialization and
immutability checks.

After static preflight validation, a native runner matrix builds and smoke-tests
`linux/amd64` on `ubuntu-24.04` and `linux/arm64` on `ubuntu-24.04-arm`.
The repository must have access to both hosted runner labels. No release step
uses QEMU: bundled Bun can fail under cross-architecture emulation.
Each runner pushes an untagged platform index by digest, with BuildKit SBOM and
maximum-mode provenance attestations. It executes `omp --version` from that
exact pushed digest and scans it natively with Trivy 0.61.1; HIGH/CRITICAL
findings fail the release. Private image pulls are explicitly authenticated.
The scan platform is explicitly set from the native architecture matrix: Trivy
otherwise defaults remote index resolution to `linux/amd64`, even on an ARM runner.
Unique per-architecture digest artifacts pass only validated images to the
publication job. That job rechecks full-tag absence, merges both platform
indexes (including their attestations) into the immutable multiarch manifest,
and captures the newly assembled manifest digest, not either input digest.
Cosign 2.4.3 signs that manifest using GitHub OIDC and the transparency log.
Compatibility tags promote only after these steps succeed.

Keyless signing records the signing identity and image digest in a public
transparency log, even when GHCR package contents remain private. Administrators
must approve that metadata disclosure before enabling the release environment.

Moving tags are evaluated **independently** against all published stable full
version tags:

- `v1.2` moves only to the newest `1.2.x` release.
- `v1` moves only to the newest `1.x` release.
- `latest` moves only to the newest stable release overall.
- Prereleases publish their immutable full tag only; they never move aliases.

For example, publishing `v1.2.4` after `v1.3.0` and `v2.0.0` updates `v1.2`,
not `v1` or `latest`. Publishing an older patch cannot roll back any alias.
The first stable release in a line publishes all eligible aliases, e.g.
`v1.2.3`, `v1.2`, `v1`, `latest`.

## Outputs and recovery

The workflow summary and GitHub release show `ghcr.io/phbergsmann/che-omp-ai-tool`
with the immutable manifest digest. Release assets are:

- `image-digest.txt`: the complete `ghcr.io/...@sha256:...` reference.
- `registry.json`: the registry rendered with that exact digest and the
  integration release tag, suitable for digest-pinned installation.

An image manifest contains both architectures; container runtimes select their
native platform. Prefer the digest reference for deployment. Full-version tags
are workflow-enforced immutable; moving aliases are intentionally not.
Administrators provide private GHCR image-pull credentials to Che/Dev Spaces;
neither image nor registry embeds credentials.

If publication failed before creating the full-version image tag, fix the
workflow on `main` and use the trusted manual release path with the existing,
unchanged integration tag. This updates orchestration without moving the source
tag or weakening validation.

A failure after the full tag has been pushed can leave an immutable, unpromoted
image without release artifacts. The workflow must not overwrite it on rerun.
Investigate the failed validation/signing/promotion step, then publish a new
integration version after fixing the cause; never delete and reuse a full tag.
Workflow source is not evidence of a successful publication: inspect the actual
Actions run, GHCR manifests and release assets before deploying.
