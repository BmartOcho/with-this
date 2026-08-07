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

    def test_intake_instructions_cover_normalize_clarify_and_alias_log(self):
        text = chat.build_context_markdown(sample_inventory(), None)
        self.assertIn("## Inventory intake", text)
        self.assertIn("Ask a clarifying question whenever an entry is ambiguous", text)
        self.assertIn("aliases.jsonl", text)
        self.assertIn('"raw"', text)
        self.assertIn("append-only", text)
        self.assertIn("vision module", text)

    def test_intake_covers_project_vocabulary_kits_and_reconciliation(self):
        text = chat.build_context_markdown(sample_inventory(), None)
        self.assertIn("prefer ITS part names", text)
        self.assertIn("matches names", text)
        self.assertIn("expand the kit into the specific values", text)
        self.assertIn("rename/merge", text)
        self.assertIn('action "corrected"', text)
        self.assertIn("reconcile", text)

    def test_photo_intake_instructions_always_present(self):
        text = chat.build_context_markdown(sample_inventory(), None)
        self.assertIn("## Photo intake — vision v1", text)
        self.assertIn('"source": "photo"', text)
        self.assertIn('"confidence"', text)
        self.assertIn("Never write unconfirmed photo entries", text)
        self.assertIn('"action": "photo"', text)
        self.assertNotIn("Staged at launch", text)

    def test_staged_photos_are_listed_in_context(self):
        text = chat.build_context_markdown(
            sample_inventory(), None, photo_names=["bench.jpg", "drawer.png"]
        )
        self.assertIn("Staged at launch: photos/bench.jpg, photos/drawer.png", text)

    def test_match_command_is_embedded_when_provided(self):
        command = (
            "PYTHONPATH=/repo /usr/bin/python3 -m partsmatcher match "
            "inventory.json projects.json"
        )
        text = chat.build_context_markdown(
            sample_inventory(), None, match_command=command
        )
        self.assertIn("run it yourself from this folder", text)
        self.assertIn(command, text)
        self.assertNotIn("The user can re-run", text)

    def test_without_match_command_keeps_user_facing_hint(self):
        text = chat.build_context_markdown(sample_inventory(), None)
        self.assertIn("The user can re-run `python -m partsmatcher match`", text)


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

    def test_workspace_gets_seeded_alias_file(self):
        seed = '{"raw": "nano", "name": "Arduino Nano"}\n'
        with tempfile.TemporaryDirectory() as tmp:
            _, calls, _, _ = self.run_chat(workdir=tmp, alias_seed_text=seed)
            self.assertEqual(
                Path(calls["cwd"], "aliases.jsonl").read_text(encoding="utf-8"), seed
            )

    def test_photos_are_staged_with_collision_handling(self):
        with tempfile.TemporaryDirectory() as source_dir:
            first = Path(source_dir, "a", "bench.jpg")
            second = Path(source_dir, "b", "bench.jpg")
            for photo in (first, second):
                photo.parent.mkdir()
                photo.write_bytes(b"\xff\xd8fake-jpeg")
            with tempfile.TemporaryDirectory() as tmp:
                _, calls, out, _ = self.run_chat(
                    workdir=tmp, photos=[first, second]
                )
                photo_dir = Path(calls["cwd"], "photos")
                self.assertEqual(
                    sorted(p.name for p in photo_dir.iterdir()),
                    ["bench-2.jpg", "bench.jpg"],
                )
                context = Path(calls["cwd"], "CLAUDE.md").read_text(encoding="utf-8")
                self.assertIn(
                    "Staged at launch: photos/bench.jpg, photos/bench-2.jpg", context
                )
                self.assertIn("2 photo(s) staged", out)

    def test_photos_get_default_kickoff_prompt(self):
        with tempfile.TemporaryDirectory() as source_dir:
            photo = Path(source_dir, "bench.jpg")
            photo.write_bytes(b"\xff\xd8fake-jpeg")
            with tempfile.TemporaryDirectory() as tmp:
                _, calls, _, _ = self.run_chat(workdir=tmp, photos=[photo])
        self.assertEqual(calls["command"][-1], chat.DEFAULT_PHOTO_PROMPT)

    def test_user_prompt_beats_default_photo_prompt(self):
        with tempfile.TemporaryDirectory() as source_dir:
            photo = Path(source_dir, "bench.jpg")
            photo.write_bytes(b"\xff\xd8fake-jpeg")
            with tempfile.TemporaryDirectory() as tmp:
                _, calls, _, _ = self.run_chat(
                    workdir=tmp, photos=[photo], prompt="Just say hi"
                )
        self.assertEqual(calls["command"][-1], "Just say hi")

    def test_context_carries_runnable_match_command_with_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, calls, _, _ = self.run_chat(workdir=tmp)
            context = Path(calls["cwd"], "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=", context)
        self.assertIn("-m partsmatcher match inventory.json projects.json", context)

    def test_no_projects_context_omits_match_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, calls, _, _ = self.run_chat(
                workdir=tmp, report=None, projects_text=None
            )
            context = Path(calls["cwd"], "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("PYTHONPATH=", context)

    def test_banner_mentions_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, out, _ = self.run_chat(workdir=tmp)
        self.assertIn("partsmatcher recover", out)

    def test_session_record_written_with_stores_and_seed_count(self):
        seed = '{"raw": "nano", "name": "Arduino Nano"}\n'
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp, "inv.json")
            aliases = Path(tmp, "inv.aliases.jsonl")
            _, calls, _, _ = self.run_chat(
                workdir=str(Path(tmp, "ws")),
                alias_seed_text=seed,
                inventory_store=store,
                alias_store=aliases,
            )
            record = json.loads(
                Path(calls["cwd"], chat.SESSION_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(record["inventory_store"], str(store))
        self.assertEqual(record["alias_store"], str(aliases))
        self.assertEqual(record["alias_seed_count"], 1)
        self.assertEqual(record["original_inventory"], "[]")

    def test_session_record_null_stores_for_sample_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, calls, _, _ = self.run_chat(workdir=tmp)
            record = json.loads(
                Path(calls["cwd"], chat.SESSION_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
        self.assertIsNone(record["inventory_store"])
        self.assertIsNone(record["alias_store"])


def editing_launch(new_inventory=None, alias_lines=(), returns=0):
    """A fake `claude` that edits workspace files, like intake mode would."""

    def _launch(command, cwd=None):
        if new_inventory is not None:
            Path(cwd, "inventory.json").write_text(new_inventory, encoding="utf-8")
        if alias_lines:
            with open(Path(cwd, "aliases.jsonl"), "a", encoding="utf-8") as handle:
                for line in alias_lines:
                    handle.write(line + "\n")
        return returns

    return _launch


class SyncBackTests(unittest.TestCase):
    ORIGINAL = json.dumps(
        {"parts": [{"name": "Red LED", "quantity": 6}]}, indent=2
    )
    UPDATED = json.dumps(
        {
            "parts": [
                {"name": "Red LED", "quantity": 6},
                {"name": "470 ohm resistor", "quantity": 25},
            ]
        },
        indent=2,
    )

    def run_sync(self, launch, *, seed="", no_store=False, sync=True):
        stack = tempfile.TemporaryDirectory()
        tmp = stack.name
        self.addCleanup(stack.cleanup)
        source = Path(tmp, "inv.json")
        source.write_text(self.ORIGINAL, encoding="utf-8")
        alias_store = Path(tmp, "inv.aliases.jsonl")
        if seed:
            alias_store.write_text(seed, encoding="utf-8")
        workdir = Path(tmp, "workspace")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = chat.run_chat(
                inventory=parse_inventory(json.loads(self.ORIGINAL)),
                inventory_text=self.ORIGINAL,
                inventory_store=None if no_store else source,
                alias_store=None if no_store else alias_store,
                alias_seed_text=seed,
                sync=sync,
                workdir=str(workdir),
                which=lambda binary: f"/usr/local/bin/{binary}",
                launch=launch,
            )
        return code, source, alias_store, workdir, stdout.getvalue()

    def test_valid_inventory_edit_syncs_back_with_backup(self):
        code, source, _, _, out = self.run_sync(
            editing_launch(new_inventory=self.UPDATED)
        )
        self.assertEqual(code, 0)
        self.assertEqual(source.read_text(encoding="utf-8"), self.UPDATED)
        backup = source.with_name("inv.json.bak")
        self.assertEqual(backup.read_text(encoding="utf-8"), self.ORIGINAL)
        self.assertIn("inventory updated", out)
        self.assertIn("1 → 2 part types, 6 → 31 parts", out)

    def test_invalid_inventory_edit_never_touches_source(self):
        code, source, _, workdir, out = self.run_sync(
            editing_launch(new_inventory="{not json")
        )
        self.assertEqual(code, 0)
        self.assertEqual(source.read_text(encoding="utf-8"), self.ORIGINAL)
        self.assertFalse(source.with_name("inv.json.bak").exists())
        self.assertIn("no longer validates", out)
        self.assertIn(str(workdir), out)

    def test_unchanged_inventory_is_left_alone(self):
        code, source, _, _, out = self.run_sync(editing_launch())
        self.assertEqual(code, 0)
        self.assertFalse(source.with_name("inv.json.bak").exists())
        self.assertNotIn("inventory updated", out)

    def test_new_alias_records_append_to_store_skipping_malformed(self):
        seed = '{"raw": "nano", "name": "Arduino Nano"}\n'
        good = '{"raw": "a strip of neopixels", "name": "WS2812B LED strip (1 m)", "quantity": 1, "action": "added"}'
        bad = "{not json"
        incomplete = '{"raw": "orphan"}'
        _, _, alias_store, _, out = self.run_sync(
            editing_launch(alias_lines=[good, bad, incomplete]), seed=seed
        )
        content = alias_store.read_text(encoding="utf-8")
        self.assertEqual(content, seed + good + "\n")
        self.assertIn("1 naming-alias record(s) appended", out)
        self.assertIn("skipped 2 malformed alias record(s)", out)

    def test_sample_source_keeps_changes_in_workspace_only(self):
        code, source, alias_store, workdir, out = self.run_sync(
            editing_launch(
                new_inventory=self.UPDATED,
                alias_lines=['{"raw": "led", "name": "Red LED"}'],
            ),
            no_store=True,
        )
        self.assertEqual(code, 0)
        self.assertEqual(source.read_text(encoding="utf-8"), self.ORIGINAL)
        self.assertFalse(alias_store.exists())
        self.assertIn("bundled sample", out)
        self.assertIn("naming-alias record(s) captured", out)

    def test_no_sync_leaves_everything_in_workspace(self):
        code, source, alias_store, workdir, out = self.run_sync(
            editing_launch(
                new_inventory=self.UPDATED,
                alias_lines=['{"raw": "led", "name": "Red LED"}'],
            ),
            sync=False,
        )
        self.assertEqual(code, 0)
        self.assertEqual(source.read_text(encoding="utf-8"), self.ORIGINAL)
        self.assertFalse(alias_store.exists())
        self.assertIn("--no-sync", out)


class RecoverTests(unittest.TestCase):
    ORIGINAL = SyncBackTests.ORIGINAL
    UPDATED = SyncBackTests.UPDATED
    SEED = '{"raw": "nano", "name": "Arduino Nano"}\n'
    NEW_ALIAS = (
        '{"raw": "buck module", "name": "LM2596 buck converter module", '
        '"quantity": 1, "action": "photo"}'
    )

    def abandoned_session(self, tmp, name="partsmatcher-chat-test", edit=True):
        """Run a session with sync suppressed — the workspace is left exactly
        as a closed terminal would leave it (session record included)."""
        source = Path(tmp, "inv.json")
        if not source.exists():
            source.write_text(self.ORIGINAL, encoding="utf-8")
        alias_store = Path(tmp, "inv.aliases.jsonl")
        if not alias_store.exists():
            alias_store.write_text(self.SEED, encoding="utf-8")
        workdir = Path(tmp, name)
        launch = editing_launch(
            new_inventory=self.UPDATED if edit else None,
            alias_lines=[self.NEW_ALIAS] if edit else (),
        )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            chat.run_chat(
                inventory=parse_inventory(json.loads(self.ORIGINAL)),
                inventory_text=self.ORIGINAL,
                inventory_store=source,
                alias_store=alias_store,
                alias_seed_text=self.SEED,
                sync=False,
                workdir=str(workdir),
                which=lambda binary: f"/usr/local/bin/{binary}",
                launch=launch,
            )
        return source, alias_store, workdir

    def recover(self, *args, **kwargs):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = chat.recover_session(*args, **kwargs)
        return code, stdout.getvalue()

    def test_explicit_workspace_syncs_files_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, alias_store, workdir = self.abandoned_session(tmp)
            code, out = self.recover(str(workdir))
            self.assertEqual(code, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), self.UPDATED)
            self.assertEqual(
                source.with_name("inv.json.bak").read_text(encoding="utf-8"),
                self.ORIGINAL,
            )
            self.assertEqual(
                alias_store.read_text(encoding="utf-8"),
                self.SEED + self.NEW_ALIAS + "\n",
            )
        self.assertIn("recovering chat session", out)
        self.assertIn("inventory updated", out)
        self.assertIn("1 naming-alias record(s) appended", out)

    def test_recover_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, alias_store, workdir = self.abandoned_session(tmp)
            self.recover(str(workdir))
            code, out = self.recover(str(workdir))
            self.assertEqual(code, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), self.UPDATED)
            self.assertEqual(
                source.with_name("inv.json.bak").read_text(encoding="utf-8"),
                self.ORIGINAL,
            )
            self.assertEqual(
                alias_store.read_text(encoding="utf-8"),
                self.SEED + self.NEW_ALIAS + "\n",
            )
        self.assertIn("already in sync", out)
        self.assertIn("nothing new to append", out)

    def test_picks_newest_workspace_when_unspecified(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _, old_ws = self.abandoned_session(
                tmp, name="partsmatcher-chat-old", edit=False
            )
            self.abandoned_session(tmp, name="partsmatcher-chat-new")
            os.utime(old_ws / chat.SESSION_FILENAME, (0, 0))
            code, out = self.recover(tmp_root=Path(tmp))
            self.assertEqual(code, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), self.UPDATED)
        self.assertIn("2 recoverable workspaces found", out)
        self.assertIn("partsmatcher-chat-new", out)

    def test_no_candidates_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PartsMatcherError) as ctx:
                chat.recover_session(tmp_root=Path(tmp))
        self.assertIn("no recoverable chat workspaces", str(ctx.exception))

    def test_workspace_without_session_record_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PartsMatcherError) as ctx:
                chat.recover_session(tmp)
        self.assertIn("not a recoverable chat workspace", str(ctx.exception))

    def test_unchanged_session_reports_nothing_to_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, alias_store, workdir = self.abandoned_session(tmp, edit=False)
            code, out = self.recover(str(workdir))
            self.assertEqual(code, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), self.ORIGINAL)
            self.assertFalse(source.with_name("inv.json.bak").exists())
        self.assertIn("nothing to recover", out)

    def test_sample_session_recovery_touches_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp, "ws")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                chat.run_chat(
                    inventory=parse_inventory(json.loads(self.ORIGINAL)),
                    inventory_text=self.ORIGINAL,
                    sync=False,
                    workdir=str(workdir),
                    which=lambda binary: f"/usr/local/bin/{binary}",
                    launch=editing_launch(
                        new_inventory=self.UPDATED, alias_lines=[self.NEW_ALIAS]
                    ),
                )
            code, out = self.recover(str(workdir))
            self.assertEqual(code, 0)
        self.assertIn("bundled sample", out)
        self.assertIn("naming-alias record(s) captured", out)


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

    def test_user_inventory_computes_persistent_stores(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp, "bench.json")
            inventory.write_text(json.dumps([{"name": "Nut", "quantity": 4}]))
            alias_store = Path(tmp, "bench.aliases.jsonl")
            alias_store.write_text('{"raw": "nut", "name": "Nut"}\n')
            with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
                self.invoke(["chat", str(inventory), "--no-projects"])
        kwargs = run_chat.call_args.kwargs
        self.assertEqual(kwargs["inventory_store"], inventory)
        self.assertEqual(kwargs["alias_store"], alias_store)
        self.assertEqual(
            kwargs["alias_seed_text"], '{"raw": "nut", "name": "Nut"}\n'
        )
        self.assertTrue(kwargs["sync"])

    def test_sample_inventory_gets_no_persistent_stores(self):
        with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
            self.invoke(["chat"])
        kwargs = run_chat.call_args.kwargs
        self.assertIsNone(kwargs["inventory_store"])
        self.assertIsNone(kwargs["alias_store"])

    def test_no_sync_flag_passes_through(self):
        with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
            self.invoke(["chat", "--no-sync"])
        self.assertFalse(run_chat.call_args.kwargs["sync"])

    def test_valid_photos_pass_through_to_run_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp, "bench.JPG")
            photo.write_bytes(b"\xff\xd8fake-jpeg")
            with mock.patch.object(chat, "run_chat", return_value=0) as run_chat:
                code, _, _ = self.invoke(["chat", "--photo", str(photo)])
        self.assertEqual(code, 0)
        self.assertEqual(run_chat.call_args.kwargs["photos"], [photo])

    def test_missing_photo_exits_2(self):
        code, _, err = self.invoke(["chat", "--photo", "/nope/bench.jpg"])
        self.assertEqual(code, 2)
        self.assertIn("photo not found", err)

    def test_unsupported_photo_type_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "scan.pdf")
            bad.write_bytes(b"%PDF-fake")
            code, _, err = self.invoke(["chat", "--photo", str(bad)])
        self.assertEqual(code, 2)
        self.assertIn("unsupported photo type", err)
        self.assertIn(".png", err)

    def test_chat_schema_error_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "inv.json")
            with open(bad, "w", encoding="utf-8") as handle:
                json.dump([{"quantity": 3}], handle)
            code, _, err = self.invoke(["chat", bad])
        self.assertEqual(code, 2)
        self.assertIn("'name' must be a non-empty string", err)

    def test_recover_routes_to_recover_session(self):
        with mock.patch.object(chat, "recover_session", return_value=0) as rec:
            code, _, _ = self.invoke(["recover"])
        self.assertEqual(code, 0)
        rec.assert_called_once_with(None)

    def test_recover_accepts_workspace_path(self):
        with mock.patch.object(chat, "recover_session", return_value=0) as rec:
            self.invoke(["recover", "/tmp/ws"])
        rec.assert_called_once_with("/tmp/ws")

    def test_recover_error_exits_2(self):
        with mock.patch.object(
            chat,
            "recover_session",
            side_effect=PartsMatcherError("no recoverable chat workspaces"),
        ):
            code, _, err = self.invoke(["recover"])
        self.assertEqual(code, 2)
        self.assertIn("no recoverable chat workspaces", err)

    def test_recover_rejects_claude_passthrough(self):
        with self.assertRaises(SystemExit) as ctx:
            self.invoke(["recover", "--", "--continue"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
