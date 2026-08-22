# PartsMatcher on a phone — architecture proposal (pre-code)

Decision doc for mobile-first PartsMatcher (Ben, 2026-08-21). Same shape as
`APP_ARCHITECTURE.md`: options, a recommendation, and open questions —
**nothing here is ratified and no code has moved.**

The ask: photograph parts at the bench with a phone, build the inventory
conversationally, see what's buildable, and pull in outside build plans —
driven by the Claude account already logged in on the phone, with no API
key. Ben also asked to fold in the open per-turn latency item (1B vs 1C).

Everything cited below was verified live against Anthropic documentation on
2026-08-21. Claims that could **not** be verified are marked UNVERIFIED and
must not be designed around until tested.

## The three facts that decide this

**1. Claude Code cannot run on a phone. Permanently, not "not yet."**
Since ~v2.1.113 it ships only as per-platform prebuilt native binaries; the
npm package is a 26KB launcher and `cli.js` no longer exists. On iOS there
is no JS entrypoint to interpret, no shell can exec an ARM64 Linux ELF, and
JIT is unavailable — three independent walls. On Android the `install.cjs`
platform key `linux-arm64-android` resolves to an unpublished package (404);
what works is a ~2GB proot Linux userland, which is a tinkerer's party trick,
not something to ship. So the choice is binary: Anthropic's surface, or the
user's own machine.

**2. A branded PartsMatcher app that signs into a Claude subscription is
prohibited.** From Anthropic's legal-and-compliance page: developers *"may
not collect, store, or intermediate Claude.ai credentials or session
tokens,"* there is no third-party "Sign in with Claude," and the Agent SDK
carries the same prohibition explicitly. This is what was enforced against
in early 2026, and the enforcement target was token reuse in custom HTTP
clients.

**3. What PartsMatcher already does is explicitly carved out as permitted.**
The load-bearing sentence: the restrictions do not *"prevent an end user
from signing in to the unmodified Claude Code binary with their own Claude
subscription."* The code satisfies this cleanly — `shutil.which` finds the
user's own binary, and no credential is ever read, stored, or forwarded.
Two conditions attach and both are met (binary unmodified; each end user on
their own credentials). One obligation is open: distributing software that
*runs* Claude Code requires agreeing to Anthropic's Commercial ToS.

Together these say: don't port the harness to a phone. Anthropic already
built the phone client, and it's the only sanctioned one.

## Decision 1 — which mobile surface

### Option 1A: Remote Control (phone drives a session on Ben's Mac)

`claude remote-control` (or `/remote-control`) on the Mac, scan the QR from
the Claude app, and drive that session from the phone. Code execution and
filesystem access stay local.

- **For:** the full local environment — `my_inventory.json`, the matcher,
  MCP servers, `@`-autocomplete of local paths. Photos attach from the phone
  and *"Claude sees attached photos directly as part of your message."*
  Pro and Max. Reconnects automatically after the machine sleeps and wakes.
- **Against:** the Mac must stay awake with Claude Code running — which is
  precisely the garage-with-the-laptop-closed case. The phone cannot select
  Bypass permissions, and `/plugin`, `/resume` and `/clear` are unavailable.

### Option 1B: Cloud sessions (repo in, laptop off)

Pick a repository and branch in the app's Code tab; an Anthropic-managed VM
clones it, works, and pushes a branch. No separate compute charge — you pay
only in shared rate limits.

- **For:** the only path in this comparison that survives the laptop being
  genuinely off. Sessions persist across devices. Repo-committed
  `.claude/skills/` **is** loaded — documented, not inferred.
- **Against:** requires GitHub (GitLab/Bitbucket can only be sent as a local
  bundle, which needs a checkout, and can't push back), so the inventory
  moves to a private GitHub repo. Still labelled research preview.
  **UNVERIFIED and load-bearing: whether a cloud session accepts a
  camera-roll photo attachment.** Anthropic's attachment language is scoped
  to Remote Control; the Claude Code on the web page has zero mentions of
  image or file upload. Five-minute test — see First milestone.

### Option 1C: Cowork

Cowork is the general-computing sibling of Claude Code, in beta on web and
mobile. Anthropic's own routing rule sends dev work to Code and keeps
documents in Cowork.

- **Against:** availability detail reached research only as search renderings
  of an egress-blocked support domain (medium confidence), whether a mobile
  Cowork session accepts camera-roll photos or can clone and push a git repo
  is unverified, and the cloud sandbox reaches local files only through the
  Desktop app on a machine that is online. Not the mobile path.

### Option 1D: bind `partsmatcher app` to the LAN or a tunnel

Serve the existing page to the phone by binding beyond loopback.

- **Against, decisively:** `partsmatcher/app/` has no authentication of any
  kind — `POST /api/end` needs no credential, writes to the real
  `my_inventory.json`, and shuts the server down. Binding it beyond loopback
  makes an unauthenticated, file-editing, shell-running endpoint. Separately:
  the moment more than one person can reach it, one subscription is being
  intermediated for several users, which is the prohibited act. There is also
  a live report that `tailscale serve` buffers SSE, which would make turns
  hang in a way that reads as a Claude bug.

**Recommendation: 1A now, 1B as well if the photo test passes.** They are
not exclusive — the same repo works under both, so the test decides how much
freedom you get, not which architecture to build.

## Decision 2 — what PartsMatcher becomes

Today PartsMatcher is the *harness*: `cli.py` gathers inputs, `chat.py`
builds a temp workspace and generates `CLAUDE.md`, `find_claude` gates on
`shutil.which`, and `subprocess` spawns the binary. Every phone problem in
this project descends from that one fact — a phone has no PATH, no temp
directory, and no TTY to hand over.

The fix is not to port the harness. It is to become the thing a harness
reads.

### The bench repo

One private git repo Ben opens from the Claude app:

```
~/bench/
  partsmatcher/                     # the stdlib package, vendored
  data/
    inventory.json                  # tracked in git
    projects.json
    inventory.aliases.jsonl
  .claude/
    skills/partsmatcher/SKILL.md    # the intake protocol
    settings.json                   # the tool allowlist
  CLAUDE.md                         # same protocol, as a hedge
```

The protocol prose currently welded into `build_context_markdown`
(`chat.py:124-352`) becomes `SKILL.md`. The frozen data snapshot inside it
(the inventory listing at 148-153, the pre-rendered report at 157-158) is
dropped — because the session runs the *real* matcher instead, which is a
strict upgrade: today the report Claude reasons from goes stale the instant
intake edits `inventory.json`, which is exactly why `match_command` had to
be bolted in at `chat.py:186-192`.

Ready-to-copy `SKILL.md` and `settings.json` live in `docs/bench-repo/`.

**What this avoids building:** an auth layer for a shell-running server, a
photo upload endpoint, responsive CSS across two mobile OS vendors, HEIC
conversion, a barcode engine, a PWA secure-context story, a second matcher
implementation, and an op-log sync protocol. Every one of those is permanent
maintenance for one person.

**What it gains that no amount of engineering buys:** voice dictation with
dirty hands, push notifications so the phone goes in a pocket during a
20-second vision turn, the native multi-select picker for a burst of eight
photos, and Share → Claude for a build-plan URL.

**The one thing it costs, and the fix.** The always-visible three-bucket
sidebar becomes prose the model may or may not produce, costing a turn to
ask for — in the product whose entire point is determinism. `SKILL.md`
therefore carries a standing, non-negotiable rule: after **any** write to
`data/`, run the matcher and emit the full three-bucket report in the CLI's
exact format, plus a one-line delta. The matcher is deterministic and
sub-200ms; the only failure mode is the model forgetting, so the format is
pinned and it is the last thing every intake turn does.

### Rejected: an offline-first PWA

Its offline premise needs a secure context, which needs Tailscale HTTPS,
which needs the Mac awake — so "works with the laptop asleep" still needs
the laptop awake for anything involving Claude. It pays for that with a
permanent two-matcher parity tax on the one component that must never
disagree (research found a real instance: Python `casefold()` maps ß→"ss"
where JS `toLowerCase()` does not), node in a Python-only CI, and a
hand-rolled sync whose bugs corrupt the real inventory nondeterministically.
Its two genuinely good ideas are prose, and are stolen below for free.

## The latency item (1B vs 1C) — closed by declining to choose

Going mobile does not answer it. It makes the question **void** on the path
recommended here and **freezes the answer to 1B** on the path kept.

On the bench repo, PartsMatcher runs no subprocess at all — Anthropic's
client owns the session loop. There is no spawn to optimize, no `--resume`
transcript to rehydrate, no long-lived child to supervise. That is 1C's
latency profile plus real token streaming, push notifications and mid-turn
interrupt, for zero lines of lifecycle code.

On the desktop app, keep 1B permanently and do not build 1C. It buys a
long-lived child to babysit — liveness, restart, backpressure, protocol
drift across weekly CLI releases — and `APP_ARCHITECTURE.md` already flagged
that "a dead process mid-session is a new failure mode `recover` doesn't
currently model."

Three honesty notes:

1. A growth term nobody wrote down: `--resume` (`runner.py:69-70`)
   rehydrates the entire prior transcript every turn, so per-turn cost is
   fixed-spawn **plus O(conversation length)**. Turn 20 costs strictly more
   than turn 2 — the pain arrives exactly as a session becomes valuable.
2. `self.turns` is incremented at `runner.py:107` and never read anywhere.
   No per-turn timing has ever actually been measured in this repo. If 1C is
   ever revisited, the honest first step is ~10 lines of wall-time logging,
   not a rewrite.
3. Comparative timings gathered during research were first-hand assertions
   against an empty workspace and could not be audited. Treat the direction
   as sound and the digits as unverified.

**Fix regardless, because both options need it:** `-p` mode's default
permission mode is documented as Manual, and PartsMatcher passes no
`--permission-mode`. Today the app relies on Manual-with-no-prompt-possible
collapsing into denial rather than on explicit behavior.

## External build plans

**Recommendation: the session web-fetches a URL the user pastes.** On the
bench repo this is free — the client already has WebFetch and WebSearch, so
it is prose in `SKILL.md`, not code.

Real API integrations are dead against the no-API-key rule: every relevant
API is credentialed (Hackaday.io mandates `X-API-Key`, DigiKey is OAuth2,
Mouser is keyed at 30 req/min, Nexar caps at 1,000 parts lifetime, JLCPCB is
approval-gated), and the sites that actually hold hobbyist build plans —
Instructables, Hackster, Adafruit Learn, SparkFun Learn, Random Nerd
Tutorials — have no project API at all. The one endpoint shaped perfectly
for this problem, Hackaday.io's `GET /projects/:id/components`, is precisely
the one that breaks the rule.

A bulk cached index is a ToS fight: Instructables prohibits scrapers and has
no site-wide content licence (authors pick their own, NonCommercial
included); Hackster licenses user content to Avnet and Hackaday to
Supplyframe, neither to us; Random Nerd Tutorials prohibits "reproduction,
transfer, distribution, or storage" without written authorization — that
word forecloses a cache by name.

Fetch-on-request inverts all of it: one page, one user, on explicit request,
at human pace. Anthropic publishes a `claude-code` user agent documented as
honouring robots.txt, so a site that has said no declines on its own. And
what reaches disk is normalized part names, integer quantities and a source
URL — facts plus a citation, never the guide's prose or images. That is
already what `projects.json` holds.

Best of all it dissolves the vocabulary problem that would sink any batch
importer. External BOMs speak the wrong language — a Kitspace 1-click-BOM
row is `C1,1,1μF 0603 X5R,Murata,GRM188R71E224KA88D`, which maps onto
"Red LED ×7" only by judgement. Translating is exactly what the alias
pipeline already does. A batch importer must guess; a session can ask.

Two hard rules for `SKILL.md`: never invent price, stock or lead time (no
distributor access — a confident fabricated shopping list is the failure
mode to design against), and always stamp the source URL and fetch date into
the project description.

**On the desktop app this needs exactly one line:** add `"WebFetch"` to
`BASE_ALLOWED_TOOLS` (`app/__init__.py:53`, currently `["Read", "Glob",
"Grep", "Edit", "Write", "MultiEdit"]`). Headless `-p` cannot show a
permission prompt, so a pasted URL is silently **denied** today.

**Honest gap:** no robots.txt or ToS page for any of these sites was read
first-hand — all were egress-blocked during research. Check from an
unrestricted network before relying on the fetch affordance, and re-check
periodically; AI-crawler directives have been churning.

## What happens to the existing code

- **`matcher.py` (304 lines) — reused unchanged, and becomes more central.**
  Its docstring already promises "No I/O lives here… keeps the matching
  reusable by other frontends." It stops being pre-rendered into `CLAUDE.md`
  and becomes a tool the session invokes mid-turn. **Do not port it to
  JavaScript.**
- **`chat.py` (1130 lines) — split, not deleted.** Extract the static
  protocol prose (124-352) so `CLAUDE.md` and `SKILL.md` compose from one
  source and cannot drift. Three lines get host-swapped: the "renders in a
  terminal" instruction becomes phone-formatting guidance,
  `SAMPLE_PROJECTS_PATH` becomes repo-relative, and `match_command` becomes
  the repo-relative invocation.
- **The sync/recover family (`chat.py:412-998`) — kept and demoted.** It
  stays in the repo, stays covered by the 95 tests in `test_chat.py`, and
  stays owned. What changes is that git replaces each of its jobs on the
  mobile path: `.bak` siblings become git history, `_pending_file_change`'s
  byte-equality becomes `git status`, and `recover` has nothing to recover
  when the session edits the real tracked file in place. Mark it frozen in
  ROADMAP; do not extend it.
- **`app/server.py`, `app/page.py`, `app/runner.py` — frozen as the desk
  surface.** Do not add `--host`, a photo endpoint, token auth, an SSE
  heartbeat, or a 1C runner. Two fixes and one addition do land: add
  `"WebFetch"` to `BASE_ALLOWED_TOOLS`; drain stderr concurrently (it is
  PIPE'd at `runner.py:35` but not read until after `wait()` at 121-125, so
  >64KB of stderr deadlocks a turn forever with `turn_busy` held); and add a
  `wait(timeout=)` with a kill path.
- **`cli.py` (597 lines)** — eventually one `init-repo` subparser.
  `_gather_session_inputs` (435-514) needs no change at all.

## First milestone — "one drawer, no laptop trip"

Hand-build the bench repo and walk the literal moment, before writing a line
of new Python. One evening.

**Step 0, five minutes, do this first because it can change the
architecture:** on the phone, start any Claude Code cloud session against
any repo and try to attach a camera-roll photo. Write down what happens. If
it works, the bench repo survives the laptop being asleep in the garage. If
it doesn't, Remote Control still works but the Mac must stay awake — decide
whether that's acceptable *before* spending a week on tooling.

Then: copy `partsmatcher/` into `~/bench/` (stdlib only, so a plain copy
needs no install), copy the real inventory/projects/aliases into `data/`,
copy `docs/bench-repo/SKILL.md` and `settings.json` into `.claude/`, paste
the protocol into a root `CLAUDE.md` as a hedge, `git init && commit`, then
`claude` + `/remote-control` and scan the QR.

Then actually go to the drawers. Photograph **one compartment**. Confirm the
parts **by voice**. Watch `inventory.json` get committed. Without touching
the laptop, ask what changed and read the three-bucket report on the phone.
Finish by finding a build plan in Safari, Share → Claude, "can I build
this?".

Write down honestly: taps from pocket to first photo sent; seconds to first
useful text; whether voice confirmation actually worked with dirty hands or
you reached for the keyboard; whether the report was readable at arm's
length; and whether a drawer-wide shot produced confident nonsense (it will
— that's the test of whether the framing rule is worded strongly enough).

**Stop condition:** if the loop feels good, spend the week on
`partsmatcher init-repo`. If the awake-Mac requirement is intolerable in the
garage, you've learned it after one evening instead of after a week of auth
work.

## Two protocol rules stolen from the rejected PWA design

Both are prose in `SKILL.md`, and both come from real measurement:

- **Framing discipline.** A 300 mm drawer at the 2576 px ceiling is
  8.6 px/mm, so a 0.5 mm SOIC character lands at ~4 px — far below the
  ~18-20 px OCR floor. Drawer-wide shots are for layout and counting; part
  numbers need one compartment filling the frame.
- **Barcode first, vision second.** DigiKey and Mouser bags carry Data
  Matrix labels encoding MPN, quantity, date code and lot code per
  ANSI MH10.8.2 / ISO 15434. That is exact data, not an inference.

Useful context for both: Claude reads images natively in 28×28 px patches,
and Opus 5 sits in the high-resolution tier — 2576 px long edge, up to 4784
visual tokens, roughly 3× the older standard tier, automatic with no opt-in.
Limits are 20 images per message and 10 MB each. Claude receives no image
metadata, so EXIF orientation must be baked into pixels.

## Open questions for Ben

1. **Does a cloud session accept a camera-roll photo?** Five minutes, and
   the highest-leverage unknown here.
2. **Does your bench actually have signal?** Walk out there with the phone.
   If it doesn't, everything above is wrong and the conversation becomes
   offline-first — three weeks, a permanent two-matcher parity tax, and it
   still can't complete the photograph-a-drawer loop without a laptop.
3. **Comfortable with the inventory and 69 alias records in a private GitHub
   repo?** Remote Control alone doesn't require it; only the cloud path does.
4. **Is a three-bucket report as chat text acceptable,** or do you genuinely
   need a persistent glanceable panel? That's the one thing the bench repo
   cannot give you. Try the standing-rule version first.
5. **Keep `partsmatcher app` at all?** Freezing costs almost nothing (it's
   written and tested), but three surfaces is a lot for one person.
6. **Accept Anthropic's Commercial ToS?** Distributing software that "runs"
   Claude Code triggers that clause on a conservative reading. It doesn't
   apply to the bench repo, where PartsMatcher never runs the binary — but
   it's live for the `app/` package.

## Hazards to pin in GATES.md

- **`--bare`.** Documented: it *"is the recommended mode for scripted and
  SDK calls, and will become the default for `-p` in a future release,"* and
  *"In bare mode, Claude Code never reads OAuth credentials or the system
  keychain."* It also skips `CLAUDE.md`, skills, hooks and MCP discovery — so
  the default flip would break both the auth premise and the
  context-injection premise of `partsmatcher app` simultaneously. Never add
  it on advice that it's "recommended for scripted callers."
- **The append-only alias contract** is enforced by prose alone, and photo
  intake generates the most alias records. `_new_alias_records` treats
  everything past `lines[alias_seed_count:]` as new, so a model that
  rewrites or reorders the seeded prefix silently corrupts the dataset being
  accumulated for a future vision scanner. Git history at least makes that
  recoverable in the bench repo, which it isn't today.
- **Vendoring drift.** The bench repo carries a *copy* of `partsmatcher/`,
  so improvements here don't reach it. Stamp a version line into the
  generated context so a stale copy is visible.
- **Research-preview exposure.** Claude Code on the web is still research
  preview; Remote Control is off by default on Team/Enterprise. None of this
  blocks a Pro/Max solo dev, but they're Anthropic's surfaces to change. The
  consolation is real: the bench repo is inert data — if a surface moves,
  the matcher, the skill and the JSON all still work from a laptop terminal.
  Blast radius is "mobile stops working," never "the product breaks."
