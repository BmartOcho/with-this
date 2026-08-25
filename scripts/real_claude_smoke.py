#!/usr/bin/env python3
"""Pre-release smoke test: the whole app loop against the REAL Claude Code.

The automated suite fakes the `claude` binary and never executes the page's
JavaScript, so a Claude Code update (a changed flag, a changed stream-json
format) can break the app while every test stays green. This script closes
that gap. Run it manually before a release:

    python scripts/real_claude_smoke.py

It plays the browser's role over real HTTP against a real
`python -m partsmatcher app` process driving your real, logged-in `claude`
binary:

    1. start the app on a throwaway inventory file
    2. fetch the page and its session token (as the browser would)
    3. send one chat turn asking Claude to add a part to inventory.json
    4. confirm the sidebar state shows the new part
    5. end the session, which syncs the workspace back to the inventory file
    6. confirm the inventory file was updated and a .bak backup was written

It prints one line per step and a final RESULT: PASS or RESULT: FAIL.
You do not need to read anything but that last line. A real Claude turn
runs, so expect the whole thing to take a minute or two.

Needs: this repo, Python 3.9+, and a `claude` binary that is installed and
logged in (the same one `partsmatcher app` would use). Nothing outside a
temp directory is touched.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_HEADER = "X-PartsMatcher-Token"

SMOKE_PART = "Smoke Test Widget"
SMOKE_QUANTITY = 3

STARTING_INVENTORY = {
    "parts": [
        {"name": "Arduino Uno", "quantity": 1},
        {"name": "Red LED", "quantity": 10},
    ]
}

PROJECTS = {
    "projects": [
        {
            "name": "Blinker",
            "parts": [
                {"name": "Arduino Uno", "quantity": 1},
                {"name": "Red LED", "quantity": 2},
            ],
        }
    ]
}

TURN_PROMPT = (
    f"Open inventory.json and add one new part entry with name "
    f"'{SMOKE_PART}' and quantity {SMOKE_QUANTITY}. Keep every existing "
    "entry exactly as it is, make no other changes, and do not edit any "
    "other file. When the edit is saved, reply with just: done"
)


class SmokeFailure(Exception):
    """A step failed; the message is the plain-English reason."""


class AppProcess:
    """The `partsmatcher app` child, with its stdout tailed on a thread."""

    def __init__(self, command: "list[str]") -> None:
        self.process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.lines: "list[str]" = []
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

    def _drain(self) -> None:
        for line in self.process.stdout:
            with self._lock:
                self.lines.append(line.rstrip("\n"))

    def output_so_far(self) -> "list[str]":
        with self._lock:
            return list(self.lines)

    def wait_for_line(self, pattern: str, timeout: float) -> str:
        """First stdout line matching `pattern`, or SmokeFailure on timeout/exit."""
        deadline = time.monotonic() + timeout
        seen = 0
        while time.monotonic() < deadline:
            lines = self.output_so_far()
            for line in lines[seen:]:
                if re.search(pattern, line):
                    return line
            seen = len(lines)
            if self.process.poll() is not None:
                raise SmokeFailure(
                    "the app process exited before it was ready "
                    f"(exit code {self.process.returncode}). Its output:\n"
                    + "\n".join(lines)
                )
            time.sleep(0.2)
        raise SmokeFailure(
            f"timed out after {timeout:.0f}s waiting for {pattern!r} in the "
            "app's output:\n" + "\n".join(self.output_so_far())
        )

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def request(
    port: int,
    method: str,
    path: str,
    *,
    token: "str | None" = None,
    body: "dict | None" = None,
    timeout: float = 30.0,
) -> "tuple[int, str]":
    """One HTTP exchange with the app; returns (status, body text)."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        headers = {}
        payload = None
        if token is not None:
            headers[TOKEN_HEADER] = token
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", errors="replace")
    finally:
        connection.close()


def sse_events(text: str) -> "list[dict]":
    """Decode the `data: {...}` frames of a text/event-stream body."""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[len("data: "):]))
            except json.JSONDecodeError:
                pass
    return events


def check(condition: bool, reason: str) -> None:
    if not condition:
        raise SmokeFailure(reason)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end smoke test against the real Claude Code."
    )
    parser.add_argument(
        "--claude-bin",
        default="claude",
        metavar="PATH",
        help="Claude Code binary to drive (default: %(default)s)",
    )
    parser.add_argument(
        "--turn-timeout",
        type=float,
        default=600.0,
        metavar="SECONDS",
        help="max seconds to wait for the Claude turn (default: %(default)s)",
    )
    args = parser.parse_args()

    # Windows consoles often use a legacy codepage; never let a stray
    # character in relayed app output crash the report itself.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    steps_total = 8
    step_number = 0

    def step(title: str) -> None:
        nonlocal step_number
        step_number += 1
        print(f"[{step_number}/{steps_total}] {title} ...", flush=True)

    print("PartsMatcher real-Claude smoke test")
    print("(this runs a real Claude turn; expect a minute or two)\n")

    temp_dir = Path(tempfile.mkdtemp(prefix="partsmatcher-smoke-"))
    app: "AppProcess | None" = None
    try:
        step("checking the claude binary is installed")
        check(
            shutil.which(args.claude_bin) is not None,
            f"could not find {args.claude_bin!r} on PATH. Install Claude "
            "Code and log in, or pass --claude-bin.",
        )

        step("starting the app on a throwaway inventory")
        inventory_file = temp_dir / "inventory.json"
        projects_file = temp_dir / "projects.json"
        original_inventory_text = json.dumps(STARTING_INVENTORY, indent=2) + "\n"
        inventory_file.write_text(original_inventory_text, encoding="utf-8")
        projects_file.write_text(
            json.dumps(PROJECTS, indent=2) + "\n", encoding="utf-8"
        )
        app = AppProcess(
            [
                sys.executable,
                "-u",  # unbuffered, so the Serving-on line reaches the pipe
                "-m",
                "partsmatcher",
                "app",
                str(inventory_file),
                str(projects_file),
                "--no-browser",
                "--port",
                "0",
                "--claude-bin",
                args.claude_bin,
            ]
        )
        serving_line = app.wait_for_line(r"Serving on http://", timeout=30)
        match = re.search(r"http://127\.0\.0\.1:(\d+)/", serving_line)
        check(match is not None, f"could not read a port from: {serving_line!r}")
        port = int(match.group(1))

        step("fetching the page and its session token (as the browser would)")
        status, page = request(port, "GET", "/")
        check(status == 200, f"GET / returned HTTP {status}, expected 200")
        token_match = re.search(r"const PM_TOKEN = '([^']+)'", page)
        check(
            token_match is not None,
            "the served page carries no session token — the page or its "
            "token embedding changed",
        )
        token = token_match.group(1)
        status, state_text = request(port, "GET", "/api/state")
        check(
            status == 200, f"GET /api/state returned HTTP {status}, expected 200"
        )
        parts_before = {
            part["name"]
            for part in json.loads(state_text)["inventory"]["parts"]
        }
        check(
            SMOKE_PART not in parts_before,
            f"{SMOKE_PART!r} is already in the starting inventory",
        )

        step("sending one chat turn to the real Claude (the slow part)")
        status, stream = request(
            port,
            "POST",
            "/api/message",
            token=token,
            body={"text": TURN_PROMPT},
            timeout=args.turn_timeout,
        )
        check(
            status == 200,
            f"POST /api/message returned HTTP {status}, expected 200",
        )
        events = sse_events(stream)
        errors = [e for e in events if e.get("type") == "error"]
        check(
            not errors,
            "the Claude turn reported an error: "
            + "; ".join(str(e.get("message")) for e in errors)
            + " (is `claude` logged in?)",
        )
        done = [e for e in events if e.get("type") == "done"]
        check(bool(done), "the Claude turn never reported it finished")
        check(
            done[-1].get("ok") is True,
            f"the Claude turn finished unsuccessfully: {done[-1]!r}",
        )

        step("confirming the app's live state shows the new part")
        status, state_text = request(port, "GET", "/api/state")
        check(
            status == 200, f"GET /api/state returned HTTP {status}, expected 200"
        )
        state = json.loads(state_text)
        check(
            "inventory_error" not in state,
            "the workspace inventory no longer parses after Claude's edit: "
            + str(state.get("inventory_error")),
        )
        added = [
            part
            for part in state["inventory"]["parts"]
            if part["name"].lower() == SMOKE_PART.lower()
        ]
        check(
            bool(added),
            f"Claude's turn finished but {SMOKE_PART!r} is not in the "
            "workspace inventory",
        )
        check(
            added[0]["quantity"] == SMOKE_QUANTITY,
            f"{SMOKE_PART!r} was added with quantity {added[0]['quantity']}, "
            f"expected {SMOKE_QUANTITY}",
        )

        step("ending the session (runs the sync back to the inventory file)")
        status, end_text = request(port, "POST", "/api/end", token=token)
        check(status == 200, f"POST /api/end returned HTTP {status}, expected 200")
        messages = json.loads(end_text)["messages"]
        check(
            any("inventory updated" in message for message in messages),
            "the end-of-session sync did not report an inventory update. "
            "It said: " + ("; ".join(messages) or "(nothing)"),
        )

        step("confirming the inventory file on disk was updated")
        app.process.wait(timeout=30)
        synced = json.loads(inventory_file.read_text(encoding="utf-8"))
        names = [part["name"].lower() for part in synced["parts"]]
        check(
            SMOKE_PART.lower() in names,
            f"the sync ran but {SMOKE_PART!r} never reached the inventory file",
        )
        check(
            "arduino uno" in names,
            "the original parts are gone from the synced inventory file",
        )

        step("confirming a .bak backup of the original inventory exists")
        backup = inventory_file.with_name(inventory_file.name + ".bak")
        check(backup.exists(), "no .bak backup was written next to the inventory")
        check(
            backup.read_text(encoding="utf-8") == original_inventory_text,
            "the .bak backup does not match the pre-session inventory",
        )

    except SmokeFailure as failure:
        print(f"\n    problem: {failure}\n")
        if app is not None:
            app.kill()
            tail = app.output_so_far()[-15:]
            if tail:
                print("last app output:")
                for line in tail:
                    print(f"    {line}")
        print(f"\n(kept for inspection: {temp_dir})")
        print("\nRESULT: FAIL")
        return 1
    except Exception:
        if app is not None:
            app.kill()
        print(f"\n(kept for inspection: {temp_dir})")
        print("\nRESULT: FAIL (unexpected error follows)")
        raise
    finally:
        if app is not None:
            app.kill()

    shutil.rmtree(temp_dir, ignore_errors=True)
    print(
        "\nEvery step passed: page served, token honored, real Claude edited "
        "the inventory, the sidebar state saw it, and the end-of-session "
        "sync wrote it back with a backup."
    )
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
