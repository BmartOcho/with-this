# Releasing PartsMatcher to PyPI

Publishing runs through `.github/workflows/release.yml` using PyPI
**Trusted Publishing** (OIDC): GitHub proves the workflow's identity to
PyPI directly, so there is no API token and no repository secret to leak
or rotate. Pushing a `v*` tag is the whole release action.

Everything below was verified against PyPI's own source (the publishing
form, its server-side validation, and the OIDC claim matching in
`pypi/warehouse`) on 2026-08-22, not just the prose docs.

## The part that is permanent

Read this before the first upload, because none of it can be undone:

- **A filename is burned forever.** `partsmatcher-0.7.1.tar.gz` can be
  uploaded exactly once, ever. Delete the release and you still cannot
  re-upload that filename — you must bump the version.
- **Deleting a project releases the name** for anyone else to claim.
- **Yank, don't delete.** A yanked release stays installable for anyone
  who pins it exactly, and installers otherwise ignore it. Yanking is
  reversible; deletion is not.
- **14-day window for adding files.** New files cannot be added to a
  release older than 14 days. Ship the sdist and wheel together.
- **A pending publisher does not reserve the name.** Until the first
  successful upload, anyone can take `partsmatcher`.

## One-time setup (browser)

Order matters in two places: verify email *before* enabling 2FA (2FA
locks self-service email changes), and enable 2FA *before* trying to add
a publisher (the form is gated on it).

1. Create an account at <https://pypi.org/account/register/>.
2. **Verify your primary email.** The Add button stays disabled without
   a verified primary email.
3. **Enable 2FA** at <https://pypi.org/manage/account/two-factor/>. Save
   the recovery codes somewhere offline; adding two methods is wise.
4. Register the pending publisher at
   <https://pypi.org/manage/account/publishing/> → **Add a new pending
   publisher** → **GitHub** tab:

   | Field | Value |
   | --- | --- |
   | PyPI Project Name | `partsmatcher` |
   | Owner | `BmartOcho` |
   | Repository name | `with-this` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   The workflow name is a **filename** — not the workflow's `name:`, and
   not a path. PyPI rejects anything containing `/` or not ending in
   `.yml`/`.yaml`.

5. Repeat on **TestPyPI**, which is a completely separate site with its
   own account and its own 2FA:
   <https://test.pypi.org/account/register/>, then
   <https://test.pypi.org/manage/account/publishing/> with the same
   values but Environment name `testpypi`.

6. On GitHub: **Settings → Environments**, create `pypi` and `testpypi`.
   On `pypi` only, add yourself under **Required reviewers** so every
   real publish waits for a click. Leave `testpypi` ungated.

## Cutting a release

1. Bump `version` in `pyproject.toml`. Update `ROADMAP.md`.
2. Locally: `python3 -m unittest` and `python3 -m build && python3 -m twine check dist/*`.
3. Commit, merge to `main`.
4. Tag and push:

   ```console
   $ git tag v0.7.1
   $ git push origin v0.7.1
   ```

5. The workflow builds, runs the suite, verifies the sdist's tests
   actually run, publishes to **TestPyPI**, then waits for your approval
   before touching PyPI.
6. Approve the `pypi` deployment. The pending publisher fires, creates
   the project, and converts itself into a normal publisher. Nothing
   further to configure — later releases just work.

**For the very first release, consider a release-candidate tag**
(`v0.7.1rc1`) so TestPyPI takes the hit if anything is misconfigured.
A real version number spent on a broken upload is spent forever.

## When the OIDC exchange fails

The action prints the claims it presented — `repository`,
`repository_owner`, `job_workflow_ref`, `environment`. Compare each
against what you registered. The usual causes:

- The workflow file was renamed, or the repository was renamed.
- The environment in the job doesn't match the registered one (or the
  job has no `environment:` while the publisher requires one).
- The publish job is being called from a **reusable workflow** — the
  filename comes from `job_workflow_ref`, so that breaks matching.
- The run came from a fork PR, which gets no OIDC token at all.

## Why the workflow is shaped this way

- **Build and publish are separate jobs.** Building inside a job that
  holds `id-token: write` is a privilege-escalation path via a poisoned
  build dependency, and PyPA explicitly calls it unsupported.
- **`id-token: write` is job-level and alone.** Unspecified permissions
  default to `none`, so the publish jobs cannot touch repo contents.
- **No `password:` input.** Passing one disables trusted publishing.
- Attestations (PEP 740) are generated and uploaded automatically for
  trusted-publishing flows; no extra configuration.
