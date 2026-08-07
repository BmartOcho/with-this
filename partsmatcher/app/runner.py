"""Drive the local Claude Code CLI headlessly, one process per turn.

Each user message becomes one `claude -p <message> --output-format
stream-json` child process run inside the chat workspace; after the first
turn, `--resume <session-id>` carries the conversation through Claude
Code's own session store. The runner parses the stream-json lines into a
small event vocabulary the app server forwards to the page:

    {"type": "session", "session_id": str}
    {"type": "text", "text": str}          # assistant prose, streamed
    {"type": "tool", "name": str}          # a tool call started
    {"type": "done", "ok": bool, "result": str}
    {"type": "error", "message": str}

Like the interactive chat mode, this never touches the Anthropic API
directly — it is the user's already-installed, already-logged-in `claude`
binary, so their subscription auth applies and no API key exists here.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Callable, Iterator, Optional, Sequence


def _default_popen(command: "Sequence[str]", cwd: str) -> "subprocess.Popen":
    return subprocess.Popen(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class ClaudeTurnRunner:
    """One headless Claude Code turn per call, resuming the same session."""

    def __init__(
        self,
        claude_path: str,
        workspace: Path,
        popen: "Callable[..., object]" = _default_popen,
    ) -> None:
        self.claude_path = claude_path
        self.workspace = Path(workspace)
        self.popen = popen
        self.session_id: "Optional[str]" = None
        self.turns = 0
        # One turn at a time: the server rejects concurrent sends, and this
        # lock backstops it.
        self.lock = threading.Lock()

    def build_command(self, message: str) -> "list[str]":
        command = [
            self.claude_path,
            "-p",
            message,
            "--output-format",
            "stream-json",
            # stream-json output requires --verbose in -p mode.
            "--verbose",
        ]
        if self.session_id:
            command += ["--resume", self.session_id]
        return command

    def _events_from_record(self, record: object) -> "Iterator[dict]":
        if not isinstance(record, dict):
            return
        session_id = record.get("session_id")
        if isinstance(session_id, str) and session_id and session_id != self.session_id:
            self.session_id = session_id
            yield {"type": "session", "session_id": session_id}
        kind = record.get("type")
        if kind == "assistant":
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    yield {"type": "text", "text": block["text"]}
                elif block.get("type") == "tool_use":
                    yield {"type": "tool", "name": block.get("name") or "tool"}
        elif kind == "result":
            yield {
                "type": "done",
                "ok": record.get("subtype") == "success"
                and not record.get("is_error"),
                "result": record.get("result") or "",
            }

    def run_turn(self, message: str) -> "Iterator[dict]":
        """Run one turn, yielding events as the child emits them."""
        with self.lock:
            command = self.build_command(message)
            try:
                process = self.popen(command, cwd=str(self.workspace))
            except OSError as exc:
                yield {"type": "error", "message": f"could not launch claude: {exc}"}
                return
            self.turns += 1
            saw_done = False
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for event in self._events_from_record(record):
                    saw_done = saw_done or event["type"] == "done"
                    yield event
            code = process.wait()
            if code != 0:
                stderr = ""
                if process.stderr is not None:
                    stderr = process.stderr.read().strip().splitlines()[-1:]
                    stderr = stderr[0] if stderr else ""
                yield {
                    "type": "error",
                    "message": f"claude exited with status {code}"
                    + (f": {stderr}" if stderr else ""),
                }
            elif not saw_done:
                yield {"type": "done", "ok": True, "result": ""}
