# Self-hosted Renovate

[The Renovate workflow](../.github/workflows/renovate.yml) runs on pushes to
`main`, every six hours (at minute 23, UTC), and on
**Actions → Renovate → Run workflow**. It is scoped to the current repository,
never discovers other repositories, and has no pull-request trigger.
A single concurrency group prevents overlapping runs.
The runner uses `renovatebot/github-action` v46.3.8, pinned to its commit, and
`ghcr.io/renovatebot/renovate:44.164.10`. No local checkout is needed: Renovate
fetches the repository and its `renovate.json` itself.

## Activate once on the default branch

1. Install the dedicated GitHub App on this repository. Grant repository
   **Contents: read and write**, **Pull requests: read and write**, and
   **Issues: read-only**. Renovate 44.164.10 queries repository issues during
   initialization even with the dependency dashboard disabled; without read
   access, GitHub rejects `repository.issues` with
   `Resource not accessible by integration`.
   Grant **Commit statuses: read-only** and **Checks: read-only** so Renovate
   can evaluate commit statuses and GitHub Actions check runs for automerge.
   Without status access, `getBranchStatus` fails with `integration-unauthorized`.
   Also grant **Workflows: write**, because the GitHub Actions manager updates
   `.github/workflows/` files. Contents read-only is insufficient for creating
   dependency-update branches. Approve changed permissions on the installation.
   The workflow requests exactly these permissions and scopes its token to this
   repository, even if the App is installed on other repositories.
2. Under repository **Settings → Secrets and variables → Actions**, configure:
   - Repository secret **`RENOVATE_APP_CLIENT_ID`**: the App's Client ID,
     available in its GitHub App settings (not its installation ID).
   - Repository secret **`RENOVATE_APP_PRIVATE_KEY`**: a generated PEM private
     key for that App, including its BEGIN/END lines.
   Never paste the private key into chat, commit it, or reuse a workstation PAT.
   A static `RENOVATE_TOKEN` secret is no longer used.
3. Disable this repository in any separately hosted Renovate installation to
   avoid duplicate bot runs. Keep other repositories unchanged. The dependency
   dashboard remains disabled; this configuration does not request Issues write
   permission.
4. Merge the workflow to the default branch and ensure Actions are enabled.
   First run **Actions → Renovate → Run workflow** with **dry-run** checked.
   After successful token creation and read-only repository processing, uncheck
   it to create update branches/PRs. Scheduled six-hourly runs are live runs;
   GitHub may delay schedules.
5. Enable **Allow auto-merge** in repository settings. Protect `main` with
   required `static` and `native-image` checks and require branches to be
   up to date before merging. These gates must exist before enabling
   automerge: platform-native automerge relies on GitHub's required checks,
   not merely the presence of CI workflows.

The pinned `actions/create-github-app-token` action mints a new installation
token for every run. It expires after about one hour and is revoked by the
action's post-job cleanup; the job timeout is 30 minutes. The workflow looks up
the App's bot account ID and sets Renovate's username and Git commit author to
that identity instead of impersonating a generic Renovate account.

Keep the private key active and rotate it through the repository secret when
needed. Missing credentials fail before Renovate starts. A token request also
fails if installation access or any requested permission is absent; App
installation alone does not supply the workflow's credentials.

The job's built-in `GITHUB_TOKEN` has only Contents read permission. It is not
the Renovate credential: PR events created using `GITHUB_TOKEN` do not
immediately trigger the normal CI workflow (GitHub may offer manual approval
instead). The App installation token lets Renovate PRs trigger CI normally.
Renovate's GitHub platform authentication supplies the GitHub datasource token,
so an additional `github.com` host rule is not needed. In particular, do not
install a broad read-only host rule that overrides the bot's write credential.

## Update behavior

The custom regex manager reads only `OMP_VERSION` and obtains published
versions from the `github-releases` datasource for `can1357/oh-my-pi`.
An OMP update changes that one canonical version file, not duplicated version
strings elsewhere. PR titles include both old and new versions, for example
`Update OMP from v18.11.1 to v18.12.0`. All OMP updates, including majors,
use GitHub's native squash automerge after the required `static` and
`native-image` checks pass on an up-to-date branch. This explicitly accepts
major-update compatibility risk beyond the smoke coverage. All dependencies
also opt in for patch and digest updates. Other minor and major updates
require manual merging. Existing recommended managers also maintain
dependencies such as GitHub Actions pins.

OMP PRs run the normal validation/native-image CI; they neither publish images
nor run cluster E2E. Once merged, an `OMP_VERSION` change on `main` triggers
tagging of that exact commit and the full [release workflow](releases.md).
Existing release-environment approval rules still apply. There is no independent
integration release version.

Renovate has no hourly PR creation limit or concurrent PR/branch limit:
`prHourlyLimit` and `prConcurrentLimit` are both `0`; the branch limit inherits
the unlimited PR limit. A live run can open all eligible updates without
waiting for hourly slots. GitHub API and Actions capacity limits still apply.
Pushes to `main` trigger live runs; the six-hour schedule and manual dispatch
also remain available.
A dry run lists candidate branches without creating them.

`rebaseWhen: "behind-base-branch"` explicitly updates stale Renovate branches
on each run. Each merge into `main` wakes Renovate again, so eligible PRs can
progress through rebase, CI, and automerge without waiting six hours.
App-authored branch updates trigger normal PR CI. The up-to-date requirement
and required checks remain enforced. Unlimited branches can cause substantial
rebase/CI activity when many PRs are open. Real conflicts or branches Renovate
cannot safely rewrite still require intervention.

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

The host login is only a temporary diagnostic credential; production uses the
fresh App token described above. Do not remove `--dry-run=full` from this
command. Remote lookup cannot validate unmerged local configuration; use the
local command for that. The manual workflow dry run also exercises the App's
actual credentials and installation permissions.

References: [official action setup and token requirements](https://github.com/renovatebot/github-action/blob/v46.3.8/README.md),
[GitHub App token action and scoped permissions](https://github.com/actions/create-github-app-token/blob/64ab729a6294000f5aa4a4bc0b73d1f32bc45510/README.md),
[Renovate self-hosted configuration and dry runs](https://docs.renovatebot.com/self-hosted-configuration/),
[GitHub platform authentication](https://docs.renovatebot.com/modules/platform/github/).
