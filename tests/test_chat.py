"""Tests for chat mode — no Claude installation is ever required to run these."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from partsmatcher import chat, cli, match, parse_inventory, parse_projects
from partsmatcher.matcher import PartsMatcherError


def sample_inventory():
    with open(cli.SAMPLE_INVENTORY, encoding="utf-8") as handle:
        return parse_inventory(json.load(handle))


def sample_report(inventory):
    with open(cli.SAMPLE_PROJECTS, encoding="utf-8") as handle:
        projects = parse_projects(json.load(handle))
    return match(inventory, projects)


class ContextMarkdownTests(unittest.TestCase):
    def test_contains_marker_inventory_and_guidance(self):
        inventory = sample_inventory()
        text = chat.build_context_markdown(inventory, sample_report(inventory))
        self.assertTrue(text.startswith(chat.CONTEXT_MARKER))
        self.assertIn("- Red LED ×6", text)
        self.assertIn("- Jumper wire ×40", text)
        self.assertIn("15 part types, 93 parts total", text)
        self.assertIn("needs 3 LEDs when the user owns 2 is short 1 LED", text)
        self.assertIn("inventory.json", text)

    def test_report_section_lists_groups_and_shortfalls(self):
        inventory = sample_inventory()
        text = chat.build_context_markdown(inventory, sample_report(inventory))
        self.assertIn("BUILD NOW (3): Blink Badge, Reaction Timer, Sunset Night-Light", text)
        self.assertIn("- LED Dice: short 1 — Red LED (have 6 of 7)", text)
        self.assertIn("NOT YET (3):", text)
        self.assertIn("4x4x4 LED Cube: short 62 across 3 part types", text)

    def test_without_projects_notes_the_absence(self):
        text = chat.build_context_markdown(sample_inventory(), None)
        self.assertIn("No project database was loaded", text)
        self.assertNotIn("BUILD NOW", text)


class WorkspaceTests(unittest.TestCase):
    def test_creates_temp_workspace_with_context_and_data(self):
        workspace = chat.prepare_workspace(
            None,
            f"{chat.CONTEXT_MARKER} -->\ncontext",
            {"inventory.json": "[]", "projects.json": "[]"},
        )
        try:
            self.assertTrue((workspace / "CLAUDE.md").is_file())
            self.assertTrue((workspace / "inventory.json").is_file())
            self.assertTrue((workspace / "projects.json").is_file())
            self.assertIn("partsmatcher-chat-", workspace.name)
        finally:
            for child in workspace.iterdir():
                child.unlink()
            workspace.rmdir()

    def test_refuses_to_overwrite_foreign_claude_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "CLAUDE.md").write_text("# My own project notes\n")
            with self.assertRaises(PartsMatcherError):
                chat.prepare_workspace(tmp, f"{chat.CONTEXT_MARKER} -->", {})
            self.assertEqual(
                Path(tmp, "CLAUDE.md").read_text(), "# My own project notes\n"
            )

    def test_overwrites_its_own_previous_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = f"{chat.CONTEXT_MARKER} -->\nold session"
            Path(tmp, "CLAUDE.md").write_text(old)
            chat.prepare_workspace(tmp, f"{chat.CONTEXT_MARKER} -->\nnew session", {})
            self.assertIn("new session", Path(tmp, "CLAUDE.md").read_text())


class RunChatTests(unittest.TestCase):
    def run_chat(self, **overrides):
        inventory = sample_inventory()
        calls = {}
        launch_returns = overrides.pop("launch_returns", 0)

        def fake_launch(command, cwd=None):
            calls["command"] = command
            calls["cwd"] = cwd
            return launch_returns

        kwargs = dict(
            inventory=inventory,
            inventory_text="[]",
            report=sample_report(inventory),
            projects_text="[]",
            which=lambda binary: f"/usr/local/bin/{binary}",
            launch=fake_launch,
        )
        kwargs.update(overrides)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = chat.run_chat(**kwargs)
        return code, calls, stdout.getvalue(), stderr.getvalue()

    def test_missing_claude_fails_gracefully_with_install_hint(self):
        code, calls, _, err = self.run_chat(which=lambda binary: None)
        self.assertEqual(code, 2)
        self.assertNotIn("command", calls)
        self.assertIn("npm install -g @anthropic-ai/claude-code", err)
        self.assertIn("python -m partsmatcher match", err)

    def test_launches_claude_inside_prepared_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, calls, out, _ = self.run_chat(workdir=tmp)
            self.assertEqual(code, 0)
            self.assertEqual(calls["command"], ["/usr/local/bin/claude"])
            self.assertEqual(Path(calls["cwd"]).resolve(), Path(tmp).resolve())
            context = Path(calls["cwd"], "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("- Red LED ×6", context)
            self.assertTrue(Path(calls["cwd"], "inventory.json").is_file())
            self.assertTrue(Path(calls["cwd"], "projects.json").is_file())
            self.assertIn("no API key", out)

    def test_prompt_and_passthrough_args_reach_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, calls, _, _ = self.run_chat(
                workdir=tmp,
                prompt="What can I build in an hour?",
                claude_args=["--model", "opus"],
            )
        self.assertEqual(
            calls["command"],
            ["/usr/local/bin/claude", "--model", "opus", "What can I build in an hour?"],
        )

    def test_propagates_claude_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _, _ = self.run_chat(workdir=tmp, launch_returns=7)
        self.assertEqual(code, 7)

    def test_keyboard_interrupt_maps_to_130(self):
        def interrupted(command, cwd=None):
            raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as tmp:
            code, _, _, _ = self.run_chat(workdir=tmp, launch=interrupted)
        self.assertEqual(code, 130)

    def test_no_projects_skips_projects_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, calls, _, _ = self.run_chat(
                workdir=tmp, report=None, projects_text=None
            )
            self.assertEqual(code, 0)
            self.assertFalse(Path(calls["cwd"], "projects.json").exists())
            context = Path(calls["cwd"], "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("No project database was loaded", context)


class CliRoutingTests(unittest.TestCase):
    def invoke(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_chat_subcommand_routes_with_sample_fallback(self):
        with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
            code, _, err = self.invoke(["chat"])
        self.assertEqual(code, 0)
        self.assertIn("using bundled sample", err)
        kwargs = run_chat.call_args.kwargs
        self.assertEqual(kwargs["inventory"].distinct_parts, 15)
        self.assertIsNotNone(kwargs["report"])
        self.assertEqual(kwargs["claude_args"], [])

    def test_passthrough_args_after_double_dash(self):
        with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
            code, _, _ = self.invoke(["chat", "--", "--continue"])
        self.assertEqual(code, 0)
        self.assertEqual(run_chat.call_args.kwargs["claude_args"], ["--continue"])

    def test_no_projects_flag_omits_report(self):
        with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
            self.invoke(["chat", "--no-projects"])
        kwargs = run_chat.call_args.kwargs
        self.assertIsNone(kwargs["report"])
        self.assertIsNone(kwargs["projects_text"])

    def test_bare_invocation_still_runs_match(self):
        code, out, _ = self.invoke([])
        self.assertEqual(code, 0)
        self.assertIn("BUILD NOW (3)", out)

    def test_match_rejects_claude_passthrough(self):
        with self.assertRaises(SystemExit) as ctx:
            self.invoke(["match", "--", "--continue"])
        self.assertEqual(ctx.exception.code, 2)

    def test_chat_schema_error_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "inv.json")
            with open(bad, "w", encoding="utf-8") as handle:
                json.dump([{"quantity": 3}], handle)
            code, _, err = self.invoke(["chat", bad])
        self.assertEqual(code, 2)
        self.assertIn("'name' must be a non-empty string", err)


if __name__ == "__main__":
    unittest.main()
