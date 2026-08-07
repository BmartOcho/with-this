"""The app's localhost HTTP server — stdlib only.

A `ThreadingHTTPServer` serving the embedded page and four JSON endpoints:

    GET  /            the app page
    GET  /api/state   inventory + match report re-read from the workspace
    POST /api/message one chat turn, streamed back as text/event-stream
    POST /api/end     run the end-of-session sync, then shut the server down

Claude edits the workspace files directly (same contract as interactive
chat), so `/api/state` recomputes the sidebar from disk after every turn
instead of tracking state in memory.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional

from ..matcher import PartsMatcherError, match, parse_inventory, parse_projects


def _report_payload(report) -> dict:
    def rows(results):
        return [
            {"name": r.name, "total_missing": r.total_missing}
            for r in results
        ]

    return {
        "build_now": rows(report.build_now),
        "almost": rows(report.almost),
        "not_yet": rows(report.not_yet),
    }


class AppState:
    """Everything the request handlers need, plus the run-once sync."""

    def __init__(
        self,
        *,
        workspace: Path,
        runner,
        almost_threshold: int,
        kickoff: "Optional[str]" = None,
        sync_callback: "Optional[Callable[[], list]]" = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.runner = runner
        self.almost_threshold = almost_threshold
        self.kickoff = kickoff
        self.kickoff_sent = False
        self._sync_callback = sync_callback
        self._sync_lock = threading.Lock()
        self.synced = False
        self.sync_messages: "list[str]" = []
        self.turn_busy = threading.Lock()
        self.server: "Optional[ThreadingHTTPServer]" = None

    def take_kickoff(self) -> "Optional[str]":
        """The kickoff prompt, handed out once so a page reload never re-fires it."""
        if self.kickoff_sent:
            return None
        self.kickoff_sent = True
        return self.kickoff

    def state_payload(self) -> dict:
        payload: dict = {
            "workspace": str(self.workspace),
            "session_id": self.runner.session_id,
            "ended": self.synced,
            "kickoff": self.take_kickoff(),
        }
        try:
            inventory = parse_inventory(
                json.loads(
                    (self.workspace / "inventory.json").read_text(encoding="utf-8")
                )
            )
            payload["inventory"] = {
                "part_types": inventory.distinct_parts,
                "total_parts": inventory.total_units,
                "parts": [
                    {"name": display, "quantity": inventory.quantities[key]}
                    for key, display in inventory.display_names.items()
                ],
            }
        except (OSError, json.JSONDecodeError, PartsMatcherError) as exc:
            # Claude may be mid-edit; the page keeps its last good sidebar.
            payload["inventory"] = {"part_types": 0, "total_parts": 0, "parts": []}
            payload["inventory_error"] = str(exc)
            payload["report"] = None
            return payload
        projects_path = self.workspace / "projects.json"
        if not projects_path.exists():
            payload["report"] = None
            return payload
        try:
            projects = parse_projects(
                json.loads(projects_path.read_text(encoding="utf-8"))
            )
            report = match(
                inventory, projects, almost_threshold=self.almost_threshold
            )
            payload["report"] = _report_payload(report)
        except (OSError, json.JSONDecodeError, PartsMatcherError) as exc:
            payload["report"] = None
            payload["report_error"] = str(exc)
        return payload

    def sync(self) -> "list[str]":
        """Run the end-of-session sync exactly once; later calls replay messages."""
        with self._sync_lock:
            if not self.synced:
                self.synced = True
                if self._sync_callback is not None:
                    self.sync_messages = list(self._sync_callback())
            return self.sync_messages

    def shutdown_server(self) -> None:
        if self.server is not None:
            # shutdown() must come from another thread than the handler's.
            threading.Thread(target=self.server.shutdown, daemon=True).start()


class AppRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> AppState:
        return self.server.app_state  # type: ignore[attr-defined]

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass  # keep the terminal quiet; the page is the UI

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            from .page import PAGE_HTML

            self._send_text(PAGE_HTML, 200, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send_json(self.state.state_payload())
        else:
            self._send_text("not found", 404, "text/plain; charset=utf-8")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:
        if self.path == "/api/message":
            self._post_message()
        elif self.path == "/api/end":
            messages = self.state.sync()
            self._send_json({"messages": messages})
            self.state.shutdown_server()
        else:
            self._send_text("not found", 404, "text/plain; charset=utf-8")

    def _post_message(self) -> None:
        if self.state.synced:
            self._send_text(
                "session already ended", 409, "text/plain; charset=utf-8"
            )
            return
        try:
            body = json.loads(self._read_body().decode("utf-8"))
            text = body["text"]
            assert isinstance(text, str) and text.strip()
        except (ValueError, KeyError, AssertionError):
            self._send_text(
                "body must be JSON: {\"text\": \"...\"}",
                400,
                "text/plain; charset=utf-8",
            )
            return
        if not self.state.turn_busy.acquire(blocking=False):
            self._send_text(
                "a turn is already in progress", 409, "text/plain; charset=utf-8"
            )
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            # Streamed response of unknown length: fall back to
            # connection-close framing.
            self.send_header("Connection", "close")
            self.end_headers()
            client_gone = False
            for event in self.state.runner.run_turn(text):
                if client_gone:
                    continue  # keep draining so the claude child never blocks
                frame = f"data: {json.dumps(event)}\n\n".encode("utf-8")
                try:
                    self.wfile.write(frame)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionError):
                    client_gone = True  # page went away; finish server-side
        finally:
            self.state.turn_busy.release()
        self.close_connection = True


def make_server(state: AppState, host: str = "127.0.0.1", port: int = 0):
    server = ThreadingHTTPServer((host, port), AppRequestHandler)
    server.app_state = state  # type: ignore[attr-defined]
    state.server = server
    return server
