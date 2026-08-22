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

## What to check before you trust it

**Step 0 first, five minutes, because it can change the architecture:** on
your phone, start any Claude Code cloud session against any repo and try to
attach a camera-roll photo. Whether that works decides whether this survives
your laptop being asleep. It is the one load-bearing thing nobody could
verify from documentation.

Then at the drawers — photograph one compartment, confirm by voice, and
watch `data/inventory.json` get committed. Write down: taps from pocket to
first photo, seconds to first useful text, whether voice actually worked
with dirty hands, whether the three-bucket report was readable at arm's
length, and whether a drawer-wide shot produced confident nonsense.

## Notes

- `settings.json` mirrors `BASE_ALLOWED_TOOLS`
  (`partsmatcher/app/__init__.py:53`) plus `WebFetch` for build-plan URLs
  and the git commands the standing rule needs. Keep the two in sync by
  hand until `init-repo` generates both from one source.
- The copied `partsmatcher/` package is a **copy**. Improvements in
  `with-this` will not reach it, and a stale matcher on the phone is
  invisible. Re-copy when the matcher changes.
- `SKILL.md` and the generated `CLAUDE.md` in `chat.py` are two hand-kept
  copies of the same protocol today. That drift is exactly what
  `partsmatcher/skill.py` is meant to remove later.
