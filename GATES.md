# Gates: app security — scoped writes and a session token

Scope: two live defects in `partsmatcher/app/`.

1. `BASE_ALLOWED_TOOLS` listed bare `Edit`/`Write`/`MultiEdit`. A bare tool
   name matches every path on the filesystem, so a prompt-injected
   headless turn could write anywhere — `~/.zshrc`, `~/.ssh/`, anything.
2. `POST /api/end` and `POST /api/message` had no token and no origin
   check. Any website open while the app runs could POST to the loopback
   port, overwrite the user's real `my_inventory.json` via the sync, and
   shut the server down.

Fix: pin writes to the session workspace with an `Edit(//<ws>/**)` rule,
and require a per-session token header plus a same-origin check on every
POST. Read-only tools stay unscoped deliberately — narrowing them risks
denying a legitimate read in headless mode, where there is no prompt to
recover from. That is a follow-up, not this change.

Depth Tree (3):
  L1  A malicious page can't drive the session; a bad turn can't escape the workspace
  L2.1  Writes scoped        -> G1, G2, G3
  L2.2  POSTs authenticated  -> G4, G5, G6, G7
  L2.3  Nothing else moved   -> G8, G9, G10
  L2.4  Proven on real Claude -> G11

- [x] G1: No bare `Edit`/`Write`/`MultiEdit` entry survives in the generated allowlist.
  CHECK: python3 -c "import json,tempfile;from pathlib import Path;from partsmatcher import app as a;t=tempfile.mkdtemp();allow=json.loads(a.write_permission_settings(Path(t)).read_text())['permissions']['allow'];print('bare_write_rules=%d' % sum(1 for e in allow if e in ('Edit','Write','MultiEdit')))"
  EXPECT: bare_write_rules=0
  EVIDENCE: bare_write_rules=0

- [x] G2: The allowlist pins writes to the session workspace with an absolute `Edit()` rule.
  CHECK: python3 -c "import json,tempfile;from pathlib import Path;from partsmatcher import app as a;t=tempfile.mkdtemp();allow=json.loads(a.write_permission_settings(Path(t)).read_text())['permissions']['allow'];r=a._workspace_edit_rule(Path(t));print('scoped_rule_present=%s shape=%s' % (r in allow, r.replace(str(Path(t).resolve()).lstrip('/'),'<WS>')))"
  EXPECT: scoped_rule_present=True shape=Edit(//<WS>/**)
  EVIDENCE: scoped_rule_present=True shape=Edit(//<WS>/**)

- [x] G3: No `Write(...)`/`MultiEdit(...)`/`NotebookEdit(...)` path rule is emitted.
  Claude Code checks file permissions against `Edit(path)` and `Read(path)`
  rules only; a path rule on the other file tools is accepted, never
  consulted, and warns at startup. Emitting one would look scoped while
  allowing nothing.
  CHECK: python3 -c "import json,tempfile;from pathlib import Path;from partsmatcher import app as a;t=tempfile.mkdtemp();allow=json.loads(a.write_permission_settings(Path(t)).read_text())['permissions']['allow'];print('unconsulted_path_rules=%d' % sum(1 for e in allow if e.startswith(('Write(','MultiEdit(','NotebookEdit('))))"
  EXPECT: unconsulted_path_rules=0
  EVIDENCE: unconsulted_path_rules=0

- [x] G4: `POST /api/end` without the token is refused, and the sync does not run.
  This is the defect with teeth: the sync writes the user's real inventory file.
  CHECK: python3 -m unittest tests.test_app.CrossSiteTests.test_end_without_token_is_refused_and_does_not_sync 2>&1 | grep -cE '^OK'
  EXPECT: 1
  EVIDENCE: 1 (asserts 403, sync_calls == [], state.synced is False)

- [x] G5: `POST /api/message` without the token is refused, and no turn runs.
  CHECK: python3 -m unittest tests.test_app.CrossSiteTests.test_message_without_token_is_refused_and_runs_no_turn 2>&1 | grep -cE '^OK'
  EXPECT: 1
  EVIDENCE: 1 (asserts 403, runner.messages == [])

- [x] G6: A foreign `Origin` is refused even when the token is correct, and the app's own origin still works.
  CHECK: python3 -m unittest tests.test_app.CrossSiteTests.test_foreign_origin_is_refused_even_with_the_token tests.test_app.CrossSiteTests.test_own_origin_is_accepted 2>&1 | grep -E '^(Ran|OK)' | tr '\n' ' '
  EXPECT: /Ran 2 tests.*OK/
  EVIDENCE: Ran 2 tests in 0.011s OK

- [x] G7: The served page carries this session's token, and both POST call sites send it.
  A page that renders but omits the header on one call site would half-work
  — chat fine, End-session broken — so both are pinned.
  CHECK: python3 -m unittest tests.test_app.CrossSiteTests.test_served_page_embeds_this_session_token tests.test_app.PageContractTests.test_page_carries_the_session_token_on_every_post 2>&1 | grep -E '^(Ran|OK)' | tr '\n' ' '
  EXPECT: /Ran 2 tests.*OK/
  EVIDENCE: Ran 2 tests in 0.005s OK

- [x] G8: The full suite passes with no test lost (baseline before this change: 158 tests, OK).
  CHECK: python3 -m unittest 2>&1 | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' '
  EXPECT: /Ran 16[0-9] tests.*OK/
  EVIDENCE: Ran 168 tests in 7.726s OK

- [x] G9: Human CLI output on the bundled samples is byte-identical to the pre-change baseline.
  The matcher and CLI are untouched; this proves it.
  CHECK: python3 -m partsmatcher > after.txt 2>&1; git stash -q; python3 -m partsmatcher > before.txt 2>&1; git stash pop -q; diff -q before.txt after.txt >/dev/null && echo human_identical=yes || echo human_identical=no
  EXPECT: human_identical=yes
  EVIDENCE: human_identical=yes

- [x] G10: JSON CLI output on the bundled samples is byte-identical to the pre-change baseline.
  CHECK: python3 -m partsmatcher --json > after.txt 2>&1; git stash -q; python3 -m partsmatcher --json > before.txt 2>&1; git stash pop -q; diff -q before.txt after.txt >/dev/null && echo json_identical=yes || echo json_identical=no
  EXPECT: json_identical=yes
  EVIDENCE: json_identical=yes

- [x] G11: **Live run** — the scoped rule actually works against a real `claude`.
  G1–G3 verify the rule's *shape*; the suite injects fakes and never
  launches Claude Code, so only a real session proves the rule is accepted
  and that writes still land unprompted. A denied write in headless mode
  can't prompt, so this failure would have been silent.
  CHECK: `python3 -m partsmatcher app` on the bundled samples; ask it to
  add parts; confirm the Edit lands, the matcher re-runs, and End-session
  syncs.
  EXPECT: Edit and Bash fire with no prompt and no denial; sidebar counts
  move; End-session returns the sync summary.
  EVIDENCE: Ben, macOS, 2026-08-22, `python3 -m partsmatcher app` on the
  bundled samples. The turn showed `Read Read Edit Bash` — the Edit landed
  and the matcher command ran, neither prompted nor denied. Inventory went
  15 → 16 part types, 93 → 98 parts (Red LED 6 → 9, Green LED ×2 new), and
  LED Dice moved into BUILD NOW. **End session & sync** returned
  "inventory changed during the session (15 → 16 part types, 93 → 98
  parts)... 2 naming-alias record(s) captured", then the app shut down —
  so requiring the token on `POST /api/end` does not break the button, and
  the bundled sample was correctly left untouched.

## Not gated here — deliberate follow-up

Read-only tools (`Read`, `Glob`, `Grep`) remain unscoped, unchanged from
before. `Grep` in particular can disclose file contents from outside the
workspace. Scoping them stays follow-up work, because a denied read in
headless mode has no prompt to recover from — the same silent failure G11
was written to rule out for writes. Do it only with another live run to
confirm reads still land.

Note for anyone reproducing G11: the session workspace is not under `/tmp`
on macOS — Python's `mkdtemp()` returns `/var/folders/.../T/` there, so a
`/tmp/partsmatcher-chat-*` glob finds nothing. Use the
`Session workspace:` path the app prints at startup.
