# Testing Patterns

**Analysis Date:** 2026-08-25

## Test Framework

**Runner:**
- stdlib `unittest` (no pytest, no third-party test deps — matches the zero-dependency house rule)
- No config file; discovery is the default `python -m unittest` from the repo root
- Each test file ends with `if __name__ == "__main__": unittest.main()` so it can run standalone

**Assertion Library:**
- `unittest.TestCase` assertions: `assertEqual`, `assertIn`/`assertNotIn` (heavily used for output/context text), `assertTrue`/`assertFalse`, `assertRaises` as a context manager

**Run Commands:**
```bash
python -m unittest                                   # whole suite (198 tests), no Claude, no network
python -m unittest tests.test_matcher                # one module
python -m unittest tests.test_app.CrossSiteTests.test_own_origin_is_accepted   # one test
python -m partsmatcher                               # CLI smoke against bundled samples
```

**CI:** `.github/workflows/tests.yml` — matrix of `ubuntu-latest`/`windows-latest` × Python `3.9`/`3.13` (oldest supported and current), running `python -m unittest` then the CLI sample smoke. New code must pass on Windows and on 3.9.

## Test File Organization

**Location:**
- Separate `tests/` package (with empty `tests/__init__.py`), mirroring source modules 1:1

**Naming:**
- Files: `tests/test_<module>.py` (`test_matcher.py`, `test_cli.py`, `test_chat.py`, `test_app.py`, `test_mcp.py`)
- Classes: `<Topic>Tests(unittest.TestCase)` — e.g. `InventoryParsingTests`, `RunChatTests`, `CrossSiteTests`, `ProtocolTests`
- Methods: long, sentence-like behavior names: `test_zero_quantity_entry_is_not_a_part_on_hand`, `test_foreign_origin_is_refused_even_with_the_token`, `test_missing_claude_fails_gracefully_with_install_hint`

**Structure:**
```
tests/
├── __init__.py          # empty, makes discovery work
├── test_matcher.py      # pure logic: parsing, normalization, grouping (292 lines)
├── test_cli.py          # end-to-end CLI via cli.main(argv) (146 lines)
├── test_chat.py         # chat context markdown, workspace, sync-back (1158 lines, largest)
├── test_app.py          # runner + live HTTP server tests (563 lines)
└── test_mcp.py          # MCP protocol/tools, in-process (363 lines)
```

## Test Structure

**Suite Organization:**
```python
# tests/test_matcher.py — module-level factory helpers, then focused classes
def make_inventory(*pairs):
    return parse_inventory([{"name": name, "quantity": qty} for name, qty in pairs])

def project_dict(name, *pairs, description=""):
    return {"name": name, "description": description,
            "parts": [{"name": part, "quantity": qty} for part, qty in pairs]}

class InventoryParsingTests(unittest.TestCase):
    def test_duplicate_names_merge_by_summing(self):
        inventory = parse_inventory([...])
        self.assertEqual(inventory.have("Red LED"), 5)
```

**Patterns:**
- Module docstrings state the isolation guarantee up front: `"""Tests for chat mode — no Claude installation is ever required to run these."""` (`tests/test_chat.py:1`); `tests/test_mcp.py:1-5` ("no Claude, no network, no subprocess")
- Shared setup lives in a base `TestCase` when several classes need it: `ServerTestCase` (`tests/test_app.py:203`) builds a workspace, fake runner, and a real `ThreadingHTTPServer` on an OS-assigned port in `setUp`, with `self.addCleanup(...)` for teardown; `ServerFixture` (`tests/test_mcp.py:47`) writes temp inventory/projects JSON and offers `call()`/`call_text()` helpers
- Cleanup via `self.addCleanup(...)` or `with tempfile.TemporaryDirectory()`, never bare `tearDown`
- Inline comments in tests document the invariant or the real bug being pinned (`tests/test_app.py:265-267`)
- Exact-output pinning: `SampleDataTests` (`tests/test_cli.py:27`) locks the out-of-the-box demo — group counts, sort order, and exact missing-part dicts

**CLI testing pattern:**
```python
# tests/test_cli.py — call main() in-process, capture streams, check exit code
def run_cli(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()
```

## Mocking

**Framework:** almost none — the codebase prefers **dependency injection over patching**. `unittest.mock` is imported only in `tests/test_chat.py`; hand-rolled fakes do the rest.

**Patterns:**
```python
# Inject fake callables through the production signatures (tests/test_chat.py:175)
def fake_launch(command, cwd=None):
    calls["command"] = command
    calls["cwd"] = cwd
    return launch_returns

chat.run_chat(..., which=lambda binary: f"/usr/local/bin/{binary}", launch=fake_launch)
```
```python
# Hand-rolled fake process/popen for the app runner (tests/test_app.py:26-47)
class FakeProcess:
    def __init__(self, stdout_text, returncode=0, stderr_text=""):
        self.stdout = io.StringIO(stdout_text)
        ...

class FakePopen:
    """Records commands; hands out canned stream-json transcripts in order."""
    def __call__(self, command, cwd):
        self.commands.append(list(command)); return self.processes.pop(0)
```
```python
# Fake runner behind a REAL HTTP server (tests/test_app.py:188-200)
class FakeRunner:
    def run_turn(self, message):
        yield {"type": "session", "session_id": "sess-fake"}
        yield {"type": "text", "text": f"echo: {message}"}
        yield {"type": "done", "ok": True, "result": f"echo: {message}"}
```

**What to Mock:**
- The `claude` binary in every form: `which` lookup, `launch` call, `popen` for stream-json turns
- Nothing else — real temp filesystems, a real `ThreadingHTTPServer` driven with `http.client`, real JSON round-trips

**What NOT to Mock:**
- The matcher (pure, tested directly), file I/O (use `tempfile`), the HTTP layer (bind a real server on port 0), the MCP server (drive `handle_message` in-process; `ServeLoopTests` uses `StringIO` stdio streams)

## Fixtures and Factories

**Test Data:**
```python
# Bundled samples double as fixtures (tests/test_chat.py:16-24)
def sample_inventory():
    with open(cli.SAMPLE_INVENTORY, encoding="utf-8") as handle:
        return parse_inventory(json.load(handle))
```
- Module-level dict constants for scenario data: `INVENTORY`/`PROJECTS` (`tests/test_mcp.py:16-40`), `TURN_ONE` canned stream-json transcript (`tests/test_app.py:50-68`)
- Small factory helpers per file: `make_inventory`/`project_dict` (`tests/test_matcher.py:14-23`), `write_json` (`tests/test_cli.py:20`), `stream_json_lines` (`tests/test_app.py:22`), `heph_bom` (`tests/test_mcp.py:43`)

**Location:**
- No `fixtures/` directory. Real sample data lives in `partsmatcher/samples/inventory.json` and `partsmatcher/samples/projects.json` and is treated as a pinned contract (tests assert exact group counts and names against it — changing samples means updating `tests/test_cli.py` and `tests/test_chat.py`)

## Coverage

**Requirements:** none enforced; no coverage tooling configured

**View Coverage:**
```bash
pip install coverage           # dev-only; not a runtime dependency
coverage run -m unittest && coverage report
```

## Test Types

**Unit Tests:**
- `tests/test_matcher.py` — pure-function tests on parsing, normalization, grouping, sort order, and every schema rejection

**Integration Tests:**
- `tests/test_cli.py` — full CLI runs in-process (argv → exit code + stdout/stderr)
- `tests/test_chat.py` — context markdown content, workspace preparation, sync-back/recover flows, CLI routing into chat
- `tests/test_app.py` — real HTTP server + fake Claude runner; includes security regression tests (`CrossSiteTests`: token, Origin, 403-before-sync)
- `tests/test_mcp.py` — JSON-RPC protocol handshake, tools list, tool calls, BOM adapter, stdio serve loop

**E2E (manual):**
- `scripts/real_claude_smoke.py` — see below

## Manual Pre-Release Smoke Test

The automated suite **fakes the `claude` binary everywhere** and never executes the app page's JavaScript, so a Claude Code update (a changed flag, a changed stream-json format) can break the app while all 198 tests stay green. `scripts/real_claude_smoke.py` closes that gap and is the required manual check before a release (see also `docs/RELEASING.md`):

```bash
python scripts/real_claude_smoke.py    # takes a minute or two; runs a real Claude turn
```

What it does (from the script's docstring, `scripts/real_claude_smoke.py:1-29`):
1. Starts a real `python -m partsmatcher app` process on a throwaway inventory in a temp dir
2. Plays the browser's role over real HTTP: fetches the page and its `X-PartsMatcher-Token`
3. Sends one chat turn asking the real, logged-in `claude` binary to add a part to `inventory.json`
4. Confirms the sidebar state shows the new part
5. Ends the session, triggering workspace sync-back
6. Confirms the inventory file was updated and a `.bak` backup was written

Output is one line per step ending in `RESULT: PASS` or `RESULT: FAIL`. Requirements: the repo, Python 3.9+, and an installed, logged-in `claude` binary. Nothing outside a temp directory is touched. This script is NOT run in CI and cannot be — it needs a real Claude Code login.

## Common Patterns

**Error Testing:**
```python
# Loop over bad values inside one test (tests/test_matcher.py:136-139)
for bad in ("2", 2.5, True, None):
    with self.assertRaises(PartsMatcherError):
        parse_inventory([{"name": "X", "quantity": bad}])

# Exit codes and stderr text, not exception types, for the CLI (tests/test_cli.py:118-121)
code, _, err = run_cli("/nonexistent/inventory.json")
self.assertEqual(code, 2)
self.assertIn("could not read inventory file", err)
```

**Generator/Event Testing:**
```python
# Consume the runner's event stream and assert the event-kind sequence (tests/test_app.py:83-88)
events = list(runner.run_turn("what can I build?"))
kinds = [event["type"] for event in events]
self.assertEqual(kinds, ["session", "text", "tool", "done"])
```

**Async Testing:**
- No asyncio in the codebase. Concurrency is tested with real threads: `ServerTestCase` runs the server in a daemon `threading.Thread`; `ConcurrentSendTests` (`tests/test_app.py:402`) exercises overlapping sends over real HTTP.

**Gates as executable checks:**
- Security/behavior changes are additionally documented in `GATES.md` with CHECK commands that invoke specific tests (e.g. `python3 -m unittest tests.test_app.CrossSiteTests.test_end_without_token_is_refused_and_does_not_sync`) and record the actual output as EVIDENCE. When fixing a bug, add the regression test, then reference it as a gate.

---

*Testing analysis: 2026-08-25*
