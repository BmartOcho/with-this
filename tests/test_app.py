"""Tests for the local app — no Claude installation or browser required.

The runner takes an injectable `popen`, and server tests drive a real
`ThreadingHTTPServer` on an OS-assigned port with a fake runner behind it.
"""

import http.client
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from partsmatcher import app as app_module
from partsmatcher import chat, cli, match, parse_inventory, parse_projects
from partsmatcher.app.runner import ClaudeTurnRunner
from partsmatcher.app.server import AppState, make_server


def stream_json_lines(*records):
    return "".join(json.dumps(record) + "\n" for record in records)


class FakeProcess:
    def __init__(self, stdout_text, returncode=0, stderr_text=""):
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode

    def wait(self):
        return self.returncode


class FakePopen:
    """Records commands; hands out canned stream-json transcripts in order."""

    def __init__(self, processes):
        self.processes = list(processes)
        self.commands = []
        self.cwds = []

    def __call__(self, command, cwd):
        self.commands.append(list(command))
        self.cwds.append(cwd)
        return self.processes.pop(0)


TURN_ONE = stream_json_lines(
    {"type": "system", "subtype": "init", "session_id": "sess-1"},
    {
        "type": "assistant",
        "session_id": "sess-1",
        "message": {
            "content": [
                {"type": "text", "text": "Hello from Claude."},
                {"type": "tool_use", "name": "Edit", "input": {}},
            ]
        },
    },
    {
        "type": "result",
        "subtype": "success",
        "session_id": "sess-1",
        "result": "Hello from Claude.",
    },
)


class RunnerTests(unittest.TestCase):
    def test_first_turn_command_and_events(self):
        popen = FakePopen([FakeProcess(TURN_ONE)])
        runner = ClaudeTurnRunner("/bin/claude", Path("/ws"), popen=popen)
        events = list(runner.run_turn("what can I build?"))
        command = popen.commands[0]
        self.assertEqual(command[:3], ["/bin/claude", "-p", "what can I build?"])
        self.assertIn("--output-format", command)
        self.assertIn("stream-json", command)
        self.assertIn("--verbose", command)
        self.assertNotIn("--resume", command)
        self.assertEqual(popen.cwds[0], str(Path("/ws")))
        kinds = [event["type"] for event in events]
        self.assertEqual(kinds, ["session", "text", "tool", "done"])
        self.assertEqual(events[0]["session_id"], "sess-1")
        self.assertEqual(events[1]["text"], "Hello from Claude.")
        self.assertEqual(events[2]["name"], "Edit")
        self.assertTrue(events[3]["ok"])

    def test_second_turn_resumes_captured_session(self):
        popen = FakePopen([FakeProcess(TURN_ONE), FakeProcess(TURN_ONE)])
        runner = ClaudeTurnRunner("/bin/claude", Path("/ws"), popen=popen)
        list(runner.run_turn("first"))
        list(runner.run_turn("second"))
        second = popen.commands[1]
        self.assertIn("--resume", second)
        self.assertEqual(second[second.index("--resume") + 1], "sess-1")

    def test_nonzero_exit_yields_error_event(self):
        popen = FakePopen([FakeProcess("", returncode=1, stderr_text="boom\n")])
        runner = ClaudeTurnRunner("/bin/claude", Path("/ws"), popen=popen)
        events = list(runner.run_turn("hi"))
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("status 1", events[-1]["message"])
        self.assertIn("boom", events[-1]["message"])

    def test_unlaunchable_binary_yields_error_event(self):
        def popen(command, cwd):
            raise OSError("no such file")

        runner = ClaudeTurnRunner("/bin/claude", Path("/ws"), popen=popen)
        events = list(runner.run_turn("hi"))
        self.assertEqual(events, [
            {"type": "error", "message": "could not launch claude: no such file"}
        ])

    def test_garbage_lines_are_skipped(self):
        text = "not json\n" + TURN_ONE
        popen = FakePopen([FakeProcess(text)])
        runner = ClaudeTurnRunner("/bin/claude", Path("/ws"), popen=popen)
        events = list(runner.run_turn("hi"))
        self.assertEqual(events[0]["type"], "session")


class PermissionSettingsTests(unittest.TestCase):
    def test_allowlist_written_with_match_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = app_module.write_permission_settings(
                Path(tmp), "python -m partsmatcher match inventory.json projects.json"
            )
            settings = json.loads(path.read_text(encoding="utf-8"))
            allow = settings["permissions"]["allow"]
            for tool in ("Read", "Edit", "Write"):
                self.assertIn(tool, allow)
            self.assertIn(
                "Bash(python -m partsmatcher match inventory.json projects.json*)",
                allow,
            )

    def test_allowlist_without_match_command_has_no_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = app_module.write_permission_settings(Path(tmp))
            allow = json.loads(path.read_text(encoding="utf-8"))["permissions"]["allow"]
            self.assertFalse(any(entry.startswith("Bash") for entry in allow))


class FakeRunner:
    """Stands in for ClaudeTurnRunner behind the server."""

    def __init__(self):
        self.session_id = None
        self.messages = []

    def run_turn(self, message):
        self.messages.append(message)
        self.session_id = "sess-fake"
        yield {"type": "session", "session_id": "sess-fake"}
        yield {"type": "text", "text": f"echo: {message}"}
        yield {"type": "done", "ok": True, "result": f"echo: {message}"}


class ServerTestCase(unittest.TestCase):
    """A live server over a real workspace with sample data copied in."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace = Path(self._tmp.name) / "workspace"
        self.workspace.mkdir()
        self.inventory_text = cli.SAMPLE_INVENTORY.read_text(encoding="utf-8")
        self.projects_text = cli.SAMPLE_PROJECTS.read_text(encoding="utf-8")
        (self.workspace / "inventory.json").write_text(
            self.inventory_text, encoding="utf-8"
        )
        (self.workspace / "projects.json").write_text(
            self.projects_text, encoding="utf-8"
        )
        self.runner = FakeRunner()
        self.sync_calls = []

        def sync_callback():
            self.sync_calls.append(True)
            return ["synced a thing"]

        self.state = AppState(
            workspace=self.workspace,
            runner=self.runner,
            almost_threshold=2,
            kickoff="kick off the session",
            sync_callback=sync_callback,
        )
        self.server = make_server(self.state)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {}
        if body is not None:
            body = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data


class ServerTests(ServerTestCase):
    def test_root_serves_page(self):
        status, data = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"PartsMatcher", data)
        self.assertIn(b"/api/message", data)

    def test_unknown_path_404s(self):
        status, _ = self.request("GET", "/nope")
        self.assertEqual(status, 404)

    def test_state_reports_inventory_and_match_groups(self):
        status, data = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        state = json.loads(data)
        inventory = parse_inventory(json.loads(self.inventory_text))
        self.assertEqual(
            state["inventory"]["part_types"], inventory.distinct_parts
        )
        self.assertEqual(state["inventory"]["total_parts"], inventory.total_units)
        report = match(inventory, parse_projects(json.loads(self.projects_text)))
        self.assertEqual(
            [row["name"] for row in state["report"]["build_now"]],
            [result.name for result in report.build_now],
        )

    def test_kickoff_is_handed_out_exactly_once(self):
        _, data = self.request("GET", "/api/state")
        self.assertEqual(json.loads(data)["kickoff"], "kick off the session")
        _, data = self.request("GET", "/api/state")
        self.assertIsNone(json.loads(data)["kickoff"])

    def test_state_survives_invalid_inventory_mid_edit(self):
        (self.workspace / "inventory.json").write_text("{ broken", encoding="utf-8")
        status, data = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        state = json.loads(data)
        self.assertIn("inventory_error", state)
        self.assertIsNone(state["report"])

    def test_message_streams_turn_events(self):
        status, data = self.request(
            "POST", "/api/message", body={"text": "hello"}
        )
        self.assertEqual(status, 200)
        frames = [
            json.loads(chunk[len("data: ") :])
            for chunk in data.decode("utf-8").split("\n\n")
            if chunk.startswith("data: ")
        ]
        self.assertEqual(
            [frame["type"] for frame in frames], ["session", "text", "done"]
        )
        self.assertEqual(frames[1]["text"], "echo: hello")
        self.assertEqual(self.runner.messages, ["hello"])

    def test_message_requires_text(self):
        status, _ = self.request("POST", "/api/message", body={"nope": 1})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/message", body={"text": "  "})
        self.assertEqual(status, 400)

    def test_end_runs_sync_once_and_blocks_further_messages(self):
        # Detach the server handle so /api/end's shutdown is a no-op and the
        # follow-up requests can still be served.
        self.state.server = None
        status, data = self.request("POST", "/api/end")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["messages"], ["synced a thing"])
        status, data = self.request("POST", "/api/end")
        self.assertEqual(json.loads(data)["messages"], ["synced a thing"])
        self.assertEqual(len(self.sync_calls), 1)
        status, _ = self.request("POST", "/api/message", body={"text": "hi"})
        self.assertEqual(status, 409)


class SlowRunner:
    """A turn that blocks until the test releases it — for the 409 guard."""

    def __init__(self):
        self.session_id = None
        self.started = threading.Event()
        self.release = threading.Event()

    def run_turn(self, message):
        self.started.set()
        self.release.wait(timeout=10)
        yield {"type": "done", "ok": True, "result": ""}


class ConcurrentSendTests(ServerTestCase):
    def test_second_send_during_a_turn_gets_409(self):
        slow = SlowRunner()
        self.state.runner = slow
        first: "dict" = {}

        def send_first():
            first["status"], first["data"] = self.request(
                "POST", "/api/message", body={"text": "long turn"}
            )

        thread = threading.Thread(target=send_first)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(slow.release.set)
        self.assertTrue(slow.started.wait(timeout=10))
        status, data = self.request("POST", "/api/message", body={"text": "again"})
        self.assertEqual(status, 409)
        self.assertIn(b"already in progress", data)
        slow.release.set()
        thread.join(timeout=10)
        self.assertEqual(first["status"], 200)
        self.assertIn(b'"done"', first["data"])


class PageContractTests(unittest.TestCase):
    def test_page_fetches_state_exactly_once_on_load(self):
        # /api/state hands the kickoff out exactly once, so the page must
        # read it from its single refreshState() fetch — a second startup
        # fetch would find the kickoff already consumed and never fire it.
        from partsmatcher.app.page import PAGE_HTML

        self.assertEqual(PAGE_HTML.count("fetch('/api/state')"), 1)
        self.assertIn("const state = await refreshState()", PAGE_HTML)


class RunAppTests(unittest.TestCase):
    def test_missing_claude_binary_errors_with_hint(self):
        inventory = parse_inventory(
            json.loads(cli.SAMPLE_INVENTORY.read_text(encoding="utf-8"))
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = app_module.run_app(
                inventory=inventory,
                inventory_text=cli.SAMPLE_INVENTORY.read_text(encoding="utf-8"),
                which=lambda name: None,
            )
        self.assertEqual(code, 2)
        self.assertIn("could not find", stderr.getvalue())

    def test_prepares_workspace_with_context_settings_and_session_record(self):
        inventory_text = cli.SAMPLE_INVENTORY.read_text(encoding="utf-8")
        projects_text = cli.SAMPLE_PROJECTS.read_text(encoding="utf-8")
        inventory = parse_inventory(json.loads(inventory_text))
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = app_module.run_app(
                    inventory=inventory,
                    inventory_text=inventory_text,
                    projects_text=projects_text,
                    workdir=tmp,
                    which=lambda name: "/bin/claude",
                    serve=False,
                )
            self.assertEqual(code, 0)
            workspace = Path(tmp)
            claude_md = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("PartsMatcher workbench session", claude_md)
            self.assertTrue((workspace / "inventory.json").exists())
            self.assertTrue((workspace / "projects.json").exists())
            self.assertTrue(
                (workspace / ".partsmatcher-session.json").exists()
            )
            settings = json.loads(
                (workspace / ".claude" / "settings.local.json").read_text(
                    encoding="utf-8"
                )
            )
            allow = settings["permissions"]["allow"]
            self.assertIn("Edit", allow)
            self.assertTrue(
                any("partsmatcher match" in entry for entry in allow)
            )
            self.assertIn("Serving on http://", stdout.getvalue())


class AppRecoverTests(unittest.TestCase):
    def test_killed_app_session_recovers_unsynced_changes(self):
        # serve=False returns before any sync runs — the same on-disk state
        # an app killed mid-session leaves behind: a session record plus
        # workspace edits that never flowed back to the user's file.
        inventory_text = cli.SAMPLE_INVENTORY.read_text(encoding="utf-8")
        inventory = parse_inventory(json.loads(inventory_text))
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "my_inventory.json"
            store.write_text(inventory_text, encoding="utf-8")
            workdir = Path(tmp) / "workspace"
            with redirect_stdout(io.StringIO()):
                code = app_module.run_app(
                    inventory=inventory,
                    inventory_text=inventory_text,
                    inventory_store=store,
                    workdir=str(workdir),
                    which=lambda name: "/bin/claude",
                    serve=False,
                )
            self.assertEqual(code, 0)
            edited = json.loads(
                (workdir / "inventory.json").read_text(encoding="utf-8")
            )
            edited["parts"][0]["quantity"] += 1
            edited_text = json.dumps(edited, indent=2)
            (workdir / "inventory.json").write_text(edited_text, encoding="utf-8")

            out = io.StringIO()
            with redirect_stdout(out):
                code = chat.recover_session(str(workdir))
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(store.read_text(encoding="utf-8")), edited
            )

            # And it stays idempotent: a second recover re-writes nothing.
            again = io.StringIO()
            with redirect_stdout(again):
                code = chat.recover_session(str(workdir))
            self.assertEqual(code, 0)
            self.assertIn("already", again.getvalue())


class CliAppTests(unittest.TestCase):
    def test_app_subcommand_is_wired(self):
        # --no-browser + injected absence of claude: exits 2 with the hint,
        # proving the subcommand parses and reaches run_app.
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(
                ["app", "--no-browser", "--claude-bin", "definitely-not-claude"]
            )
        self.assertEqual(code, 2)
        self.assertIn("definitely-not-claude", stderr.getvalue())

    def test_chat_still_works_after_input_refactor(self):
        # The shared input gatherer must keep chat behavior: missing photo
        # errors cleanly.
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["chat", "--photo", "/nope/missing.jpg"])
        self.assertEqual(code, 2)
        self.assertIn("photo not found", stderr.getvalue())
