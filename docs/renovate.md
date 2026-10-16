# Self-hosted Renovate

[The Renovate workflow](../.github/workflows/renovate.yml) runs every six hours
(at minute 23, UTC) and on **Actions → Renovate → Run workflow**. It is scoped
to the current repository, never discovers other repositories, and has no push
or pull-request trigger. A single concurrency group prevents overlapping runs.
The runner uses `renovatebot/github-action` v46.3.8, pinned to its commit, and
`ghcr.io/renovatebot/renovate:44.164.10`. No local checkout is needed: Renovate
fetches the repository and its `renovate.json` itself.

## Activate once on the default branch

1. Create a dedicated fine-grained PAT for the repository owner, selecting only
   this repository. Grant repository **Contents: read and write** and
   **Pull requests: read and write** (Metadata read access is implicit).
   Also grant **Workflows: read and write**, because the existing GitHub Actions
   manager can update `.github/workflows/` files. No organization-wide access,
   administration, package write, or Issues write permission is required.
   The dependency dashboard is disabled so the bot does not need to create issues.
   Use an explicit expiration and rotate the token before it expires.
2. Save this purpose-created credential as repository **Settings → Secrets and
   variables → Actions → New repository secret → `RENOVATE_TOKEN`**.
   Do not copy the developer workstation's `gh` credential into repository
   secrets. The workflow fails clearly if the secret is absent.
3. Disable/remove this repository from the hosted Renovate GitHub App before
   enabling the self-hosted schedule, to avoid two bots maintaining duplicate
   branches and PRs. Keep other repositories' App installations unchanged.
4. Merge the workflow and configuration to the default branch and ensure
   repository Actions are enabled. Scheduled workflows run only from that branch;
   GitHub may delay scheduled runs. Manually run **Renovate** with the default
   **dry-run** checkbox enabled first and inspect its logs. Uncheck it to allow
   branch and PR creation. Subsequent scheduled runs are live runs.

A GitHub App installation token with equivalent repository permissions can also
be supplied as `RENOVATE_TOKEN`, with the App installed only on this repository.
Installation tokens expire after about one hour: a static secret containing one
is suitable only for an immediate run, not an unattended schedule. For durable
App-based operation an administrator must arrange fresh token issuance before
each run (rather than storing the App private key in `RENOVATE_TOKEN`). The
workflow as committed uses the dedicated PAT for unattended operation.

The job's built-in `GITHUB_TOKEN` has only Contents read permission. It is not
the Renovate credential: PR events created using `GITHUB_TOKEN` do not
immediately trigger the normal CI workflow (GitHub may offer manual approval
instead). The separate PAT/App token lets Renovate PRs trigger CI normally.
Renovate's GitHub platform authentication supplies the GitHub datasource token,
so an additional `github.com` host rule is not needed. In particular, do not
install a broad read-only host rule that overrides the bot's write credential.

## Update behavior

The custom regex manager reads only `OMP_VERSION` and obtains published
versions from the `github-releases` datasource for `can1357/oh-my-pi`.
An OMP update changes that one canonical version file, not duplicated version
strings elsewhere. PR titles include both old and new versions, for example
`Update OMP from v18.11.1 to v18.12.0`. All OMP updates, including majors,
require review; OMP automerge is explicitly disabled. Existing recommended
managers also maintain other dependencies such as GitHub Actions pins.

OMP PRs run the normal validation/native-image CI; they neither publish images
nor run cluster E2E. Publishing remains a separately approved release operation
using the upstream OMP tag. There is no independent integration release version.

## Read-only runtime diagnosis

To inspect the **working tree's** configuration and upstream release lookup,
run this from the repository root with Node.js available and an existing `gh`
login. The host credential is passed only to this process; it is not written to
a file or saved as a repository secret:

```sh
GITHUB_COM_TOKEN="$(gh auth token --hostname github.com)" \
  LOG_LEVEL=debug npx --yes renovate@44.164.10 \
  --platform=local --dry-run=lookup
```

Local-platform lookup does not create branches, issues, PRs, or releases. Check
logs for the regex manager's `can1357/oh-my-pi` dependency, its current value,
and GitHub release lookup. npm and Renovate may write local caches.

To exercise the **committed default-branch** configuration against the private
GitHub repository without remote writes, use:

```sh
RENOVATE_TOKEN="$(gh auth token --hostname github.com)" \
  RENOVATE_ONBOARDING=false RENOVATE_REQUIRE_CONFIG=required \
  LOG_LEVEL=debug npx --yes renovate@44.164.10 \
  --platform=github --autodiscover=false --dry-run=full \
  phbergsmann/che-omp-ai-tool
```

The host login is only a temporary diagnostic credential; production must use
the dedicated secret above. Do not remove `--dry-run=full` from this command.
Remote lookup cannot validate unmerged local configuration; use the local
command for that. The manual workflow's dry-run input provides the same full
read-only behavior with the configured dedicated secret.

References: [official action setup and token requirements](https://github.com/renovatebot/github-action/blob/v46.3.8/README.md),
[Renovate self-hosted configuration and dry runs](https://docs.renovatebot.com/self-hosted-configuration/),
[GitHub platform authentication](https://docs.renovatebot.com/modules/platform/github/).
