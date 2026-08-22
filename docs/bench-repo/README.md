# Bench repo — ready-to-copy files

The two files beside this one are the hand-build kit for the first
milestone in [`../MOBILE.md`](../MOBILE.md): driving PartsMatcher from a
phone, at the workbench, with no laptop trip.

Nothing here is wired into the package. These are files you copy into a
separate private repo, by hand, for one evening's experiment — deliberately
so, because the point of the milestone is to feel the loop before paying to
make it reproducible. `partsmatcher init-repo` only earns its keep if the
evening goes well.

## Setup

```console
$ mkdir ~/bench && cd ~/bench
$ cp -R /path/to/with-this/partsmatcher .          # stdlib only — no install step
$ mkdir data
$ cp ~/my_inventory.json            data/inventory.json
$ cp ~/my_projects.json             data/projects.json
$ cp ~/my_inventory.aliases.jsonl   data/inventory.aliases.jsonl
$ mkdir -p .claude/skills/partsmatcher
$ cp /path/to/with-this/docs/bench-repo/SKILL.md      .claude/skills/partsmatcher/
$ cp /path/to/with-this/docs/bench-repo/settings.json .claude/
$ cp .claude/skills/partsmatcher/SKILL.md CLAUDE.md   # hedge: read from cwd regardless
$ git init && git add -A && git commit -m "Bench repo"
```

Then, in that directory:

```console
$ claude
> /remote-control
```

Press space for the QR code and scan it from the Claude app.

For the cloud-session path (laptop off), also push it to a **private GitHub
repo** — cloud sessions clone from GitHub, and GitLab/Bitbucket can't push
results back.

## What to check before you trust it

**The camera-roll photo test passed (Ben, 2026-08-22):** a cloud session
accepts a photo attached from the phone. The laptop-off path is real.

At the drawers — photograph one compartment, confirm by voice, and watch
`data/inventory.json` get committed. Write down: taps from pocket to first
photo, seconds to first useful text, whether voice actually worked with
dirty hands, whether the three-bucket report was readable at arm's length,
and whether a drawer-wide shot produced confident nonsense.

Two things to watch on the first cloud run specifically:

- **Did it push to `main`, or open a branch?** A cloud session's default is
  to commit on an auto-generated `claude/<slug>-<suffix>` branch and push
  that, with no PR opened. `SKILL.md` instructs it to push straight to
  `main` instead, and auto mode (the default on Pro/Max since 2026-08-14)
  permits default-branch pushes — but the direct-to-`main` push itself was
  never tested end to end, only branch-creating pushes were. If it opens a
  branch anyway, the loop still works; it just costs a merge you can't do
  from the Claude app.
- **Did the matcher run without a prompt?** Cloud sessions offer only
  Accept edits, Plan and Auto — never Bypass. Accept edits pre-approves
  file edits but *not* arbitrary Bash, so the matcher can prompt there;
  Auto normally lets it through. The `allowed-tools:` line in `SKILL.md`
  frontmatter is the reliable belt: skill `allowed-tools` is never gated on
  workspace trust, whereas `settings.json` `permissions.allow` may be — and
  a cloned cloud repo starts untrusted.

## Notes

- `settings.json` mirrors `BASE_ALLOWED_TOOLS`
  (`partsmatcher/app/__init__.py:53`) plus `WebFetch` for build-plan URLs
  and the git commands the standing rule needs. Keep the two in sync by
  hand until `init-repo` generates both from one source. It is read in a
  cloud session (it's part of the clone), but treat it as the belt and
  `SKILL.md`'s `allowed-tools:` as the suspenders — repo `permissions.allow`
  rules are gated on workspace trust, and the docs never resolve what a
  freshly cloned cloud repo counts as.
- Cloud sessions run Ubuntu 24.04 with Python preinstalled (3.11.15
  observed 2026-08-22; the docs promise only "Python 3.x"). A stdlib-only
  package needs no install step — `python3 -m partsmatcher` just works.
- The copied `partsmatcher/` package is a **copy**. Improvements in
  `with-this` will not reach it, and a stale matcher on the phone is
  invisible. Re-copy when the matcher changes.
- `SKILL.md` and the generated `CLAUDE.md` in `chat.py` are two hand-kept
  copies of the same protocol today. That drift is exactly what
  `partsmatcher/skill.py` is meant to remove later.
