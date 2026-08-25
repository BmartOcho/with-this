"""The PartsMatcher local app: embedded chat over the existing workspace.

`python -m partsmatcher app` prepares a chat workspace exactly as the
interactive `chat` command does — generated CLAUDE.md context, copies of
the data files, a session record for `recover` — then serves a localhost
page instead of handing over the terminal. Each message the page sends
runs one headless `claude -p --resume` turn (see `runner.py`); Claude
edits the same workspace files, so sync-back, alias logging, and
`recover` are the unchanged chat machinery.

Sync triggers: the page's "End session & sync" button, or a clean server
shutdown (Ctrl-C in the terminal). An unclean exit leaves the session
record behind for `python -m partsmatcher recover`, same as chat.

Zero dependencies throughout: `http.server`, `subprocess`, and an
embedded static page.
"""

from __future__ import annotations

import json
import shlex
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..chat import (
    CLAUDE_NOT_FOUND_HINT,
    DEFAULT_KICKOFF_PROMPT,
    DEFAULT_PHOTO_PROMPT,
    _count_records,
    _guard_claude_md,
    _resolve_workspace_dir,
    _sync_aliases,
    _sync_inventory,
    _sync_projects,
    _write_session_record,
    build_context_markdown,
    find_claude,
    prepare_workspace,
    stage_photos,
)
from ..matcher import DEFAULT_ALMOST_THRESHOLD, Inventory, MatchReport
from .runner import ClaudeTurnRunner
from .server import AppState, make_server

SETTINGS_RELPATH = Path(".claude") / "settings.local.json"

# Headless turns can't show interactive permission prompts, so the
# workspace pre-allows exactly what sessions already do today: editing the
# workspace's own files and re-running the deterministic matcher.
#
# Read-only tools stay unscoped (they were before, and narrowing them
# risks denying a legitimate read with no prompt to recover from), but
# every WRITE is pinned to this session's workspace — see
# `_workspace_edit_rule`.
BASE_ALLOWED_TOOLS = ["Read", "Glob", "Grep"]


def _workspace_edit_rule(workspace: Path) -> str:
    """The allow rule that pins file writes to `workspace`.

    Claude Code checks file permissions against `Edit(path)` and
    `Read(path)` rules *only* — a `Write(...)` or `MultiEdit(...)` path
    rule is accepted but never consulted — so `Edit()` is the rule that
    actually binds the Write and MultiEdit tools too. A bare `Write`
    would match every path on the filesystem, which is what this
    replaces.

    `//` is the absolute-path anchor, so `/tmp/ws` becomes `//tmp/ws/**`.
    Claude Code matches rules against POSIX-normalized paths: on Windows,
    `C:\\Users\\ws` is compared as `/c/Users/ws` (forward slashes, lowercase
    drive), so the rule must be emitted in that form — a `C:\\` rule is
    accepted but never matches, which would deny every headless write.
    """
    resolved = Path(workspace).resolve()
    drive = resolved.drive
    if len(drive) == 2 and drive[1] == ":":  # a Windows drive-letter path
        rest = resolved.as_posix()[len(drive):].lstrip("/")
        absolute = f"{drive[0].lower()}/{rest}"
    else:
        absolute = resolved.as_posix().lstrip("/")
    return f"Edit(//{absolute}/**)"


def write_permission_settings(
    workspace: Path, match_command: "Optional[str]" = None
) -> Path:
    """Write the workspace tool allowlist headless mode needs."""
    allow = list(BASE_ALLOWED_TOOLS)
    allow.append(_workspace_edit_rule(workspace))
    if match_command:
        allow.append(f"Bash({match_command}*)")
    settings_path = workspace / SETTINGS_RELPATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"permissions": {"allow": allow}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings_path


def run_app(
    *,
    inventory: Inventory,
    inventory_text: str,
    report: "Optional[MatchReport]" = None,
    projects_text: "Optional[str]" = None,
    inventory_store: "Optional[Path]" = None,
    projects_store: "Optional[Path]" = None,
    alias_store: "Optional[Path]" = None,
    alias_seed_text: str = "",
    almost_threshold: int = DEFAULT_ALMOST_THRESHOLD,
    sync: bool = True,
    photos: "Sequence[Path]" = (),
    workdir: "Optional[str]" = None,
    prompt: "Optional[str]" = None,
    claude_bin: str = "claude",
    port: int = 0,
    open_browser: bool = True,
    which: "Callable[[str], Optional[str]]" = None,
    popen: "Callable[..., object]" = None,
    serve: bool = True,
) -> int:
    """Prepare the workspace, serve the app, sync back on the way out.

    `which` and `popen` are injectable so tests never need Claude
    installed; `serve=False` stops before `serve_forever` for tests that
    drive the server thread themselves.
    """
    import shutil as _shutil

    claude_path = find_claude(
        claude_bin, which=which if which is not None else _shutil.which
    )
    if claude_path is None:
        print(CLAUDE_NOT_FOUND_HINT.format(binary=claude_bin), file=sys.stderr)
        return 2

    workspace = _resolve_workspace_dir(workdir)
    _guard_claude_md(workspace)
    staged_photos = stage_photos(workspace, photos)
    match_command = None
    if projects_text is not None:
        package_root = Path(__file__).resolve().parent.parent.parent
        match_command = (
            f"PYTHONPATH={shlex.quote(str(package_root))} "
            f"{shlex.quote(sys.executable or 'python3')} -m partsmatcher "
            "match inventory.json projects.json"
        )
    context = build_context_markdown(
        inventory,
        report,
        photo_names=staged_photos,
        match_command=match_command,
        projects_loaded=projects_text is not None,
        projects_store_name=None if projects_store is None else projects_store.name,
    )
    data_files = {"inventory.json": inventory_text, "aliases.jsonl": alias_seed_text}
    if projects_text is not None:
        data_files["projects.json"] = projects_text
    prepare_workspace(str(workspace), context, data_files)
    write_permission_settings(workspace, match_command)
    _write_session_record(
        workspace,
        inventory_text=inventory_text,
        inventory_store=inventory_store,
        alias_store=alias_store,
        alias_seed_count=_count_records(alias_seed_text),
        projects_text=projects_text,
        projects_store=projects_store,
    )

    if staged_photos and not prompt:
        prompt = DEFAULT_PHOTO_PROMPT
    elif not prompt:
        prompt = DEFAULT_KICKOFF_PROMPT

    def run_sync() -> "list[str]":
        messages = _sync_inventory(
            workspace,
            original_inventory_text=inventory_text,
            inventory_store=inventory_store,
        )
        messages += _sync_projects(
            workspace,
            original_projects_text=projects_text,
            projects_store=projects_store,
        )
        messages += _sync_aliases(
            workspace,
            alias_seed_count=_count_records(alias_seed_text),
            alias_store=alias_store,
        )
        return messages

    runner_popen = {} if popen is None else {"popen": popen}
    runner = ClaudeTurnRunner(claude_path, workspace, **runner_popen)
    state = AppState(
        workspace=workspace,
        runner=runner,
        almost_threshold=almost_threshold,
        kickoff=prompt,
        sync_callback=run_sync if sync else None,
    )
    server = make_server(state, port=port)
    host, bound_port = server.server_address[:2]
    url = f"http://{host}:{bound_port}/"

    print(
        f"PartsMatcher app — {inventory.distinct_parts} part types "
        f"({inventory.total_units} parts) loaded as context."
    )
    print(f"Session workspace: {workspace}")
    print(f"Serving on {url} (Ctrl-C to stop; the page's End-session button syncs too)")
    print(
        "(If the app dies before a clean exit, `python -m partsmatcher "
        "recover` syncs the session back afterward.)"
    )
    if not serve:
        return 0
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if sync:
            for message in state.sync():
                print(message)
            if not state.sync_messages:
                print("nothing to sync — the session left no changes")
        else:
            print(f"(--no-sync: any changes stay in the workspace at {workspace})")
    return 0
