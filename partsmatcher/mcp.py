"""Serve the matcher as MCP tools over stdio, for Claude Code sessions.

The Model Context Protocol server behind `partsmatcher mcp`: three
deterministic tools — ``get_inventory``, ``match_projects``,
``check_bom`` — that any MCP client (a Claude Code session anywhere on
the machine, including one embedded in another program's UI) can call.
The model never computes a match itself; these tools are the only way
to get a verdict, which enforces the chat protocol's standing rule
structurally instead of by prose.

Transport is MCP stdio: one JSON-RPC 2.0 message per line on
stdin/stdout, UTF-8. Diagnostics go to stderr, which the transport
ignores. Register once, machine-wide:

    claude mcp add --scope user partsmatcher -- \\
        python -m partsmatcher mcp /path/to/inventory.json /path/to/projects.json

Inventory and projects are re-read from disk on every tool call, so a
session that edits the files mid-conversation sees its own changes in
the next verdict.

``check_bom`` accepts the BOM format emitted by HEPH's ship step
(``{"lines": [{"key", "description", "qty", ...}]}``): each line
carries a machine id ("key") and a human name ("description"), and the
adapter prefers whichever spelling the inventory actually recognizes —
inventories speak human, but either might be the user's vocabulary.
Matching is exact-name only, deliberately: the NOT OWNED misses it
prints, with closest-name hints, are the naming-alias problem shown
honestly rather than papered over by fuzzy matching.

No third-party dependencies, in keeping with the project-wide rule.
"""

from __future__ import annotations

import contextlib
import difflib
import io
import json
import sys
from pathlib import Path

from .matcher import (
    DEFAULT_ALMOST_THRESHOLD,
    Inventory,
    PartsMatcherError,
    evaluate,
    match,
    normalize_name,
    parse_inventory,
    parse_projects,
)

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "partsmatcher", "version": "0.1.0"}

TOOLS = [
    {
        "name": "get_inventory",
        "description": (
            "List the electronics parts the user actually owns, from their "
            "inventory file (the source of truth). Optional case-insensitive "
            "substring filter on part names. Use this instead of guessing "
            "or remembering what they own."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "case-insensitive substring filter on part names"
                    ),
                }
            },
        },
    },
    {
        "name": "match_projects",
        "description": (
            "Run the deterministic three-bucket report (BUILD NOW / ALMOST "
            "THERE / NOT YET) of the user's project database against their "
            "real inventory. Never state a match result from memory — call "
            "this and read its output."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_bom",
        "description": (
            "Check a bill of materials against the user's real inventory: "
            "which lines are OWNED, SHORT, or NOT OWNED, with a net "
            "shopping list of only what must actually be bought. Accepts "
            "the HEPH out/bom.json format. Pass bom_path (a file path) or "
            "bom_json (the BOM object inline). Call it whenever the user "
            "asks whether they can build a design."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bom_path": {
                    "type": "string",
                    "description": "path to a bom.json file",
                },
                "bom_json": {
                    "type": "object",
                    "description": "a BOM object, inline",
                },
            },
        },
    },
]


# --------------------------------------------------------------------------- #
# BOM adaptation — HEPH's bom.json onto the matcher's project contract
# --------------------------------------------------------------------------- #

def bom_as_project(bom: dict, known_keys: "set[str]") -> dict:
    """Map a HEPH-format BOM onto the matcher's project contract.

    Each line carries two spellings: "key" (a catalogue machine id such
    as ``arduino_uno``) and "description" (the human name). Prefer
    whichever spelling the inventory recognizes, description first when
    neither does.
    """
    if not isinstance(bom, dict) or not isinstance(bom.get("lines"), list):
        raise PartsMatcherError("not a HEPH bom.json (no 'lines' array)")
    parts = []
    for line in bom["lines"]:
        if not isinstance(line, dict):
            continue
        candidates = [
            str(line.get(field) or "").strip()
            for field in ("description", "key")
        ]
        candidates = [c for c in candidates if c]
        name = next(
            (c for c in candidates if normalize_name(c) in known_keys),
            candidates[0] if candidates else "",
        )
        try:
            qty = int(line.get("qty", 0))
        except (TypeError, ValueError):
            continue
        if name and qty >= 1:
            parts.append({"name": name, "quantity": qty})
    if not parts:
        raise PartsMatcherError("BOM has no purchasable lines to check")
    return {
        "name": str(bom.get("name") or "design"),
        "description": "",
        "parts": parts,
    }


def check_bom_text(bom: dict, inventory: Inventory) -> str:
    """The OWNED / SHORT / NOT OWNED verdict for one BOM, as text."""
    [project] = parse_projects(
        [bom_as_project(bom, set(inventory.quantities))]
    )
    result = evaluate(project, inventory)
    missing_by_key = {normalize_name(m.name): m for m in result.missing}
    total_lines = len(project.requirements)

    owned, short, not_owned = [], [], []
    for key, required in sorted(project.requirements.items()):
        display = project.display_names[key]
        gap = missing_by_key.get(key)
        if gap is None:
            owned.append((display, required))
        elif gap.have > 0:
            short.append((display, required, gap.have))
        else:
            not_owned.append((display, required))

    verdict = (
        "BUILD NOW"
        if result.buildable
        else (
            f"short {result.total_missing} part(s) across "
            f"{result.missing_kinds} type(s)"
        )
    )
    inv_names = sorted(name for _, name, _ in inventory.on_hand())

    lines = [f"Design: {project.name}", f"Verdict: {verdict}", ""]
    lines.append(f"OWNED — nothing to buy ({len(owned)}/{total_lines})")
    for name, req in owned:
        lines.append(f"  [OK] {name} x{req}")
    lines.append("")
    lines.append(
        f"SHORT — own some, buy the rest ({len(short)}/{total_lines})"
    )
    for name, req, have in short:
        lines.append(f"  [~] {name}: have {have} of {req} (buy {req - have})")
    lines.append("")
    lines.append(
        f"NOT OWNED — the net shopping list ({len(not_owned)}/{total_lines})"
    )
    for name, req in not_owned:
        lines.append(f"  [X] {name} x{req}")
        hints = difflib.get_close_matches(name, inv_names, n=2, cutoff=0.4)
        if hints:
            lines.append(
                f"      closest inventory names: {', '.join(hints)}"
                "  <- possible rename or substitution, not a match"
            )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# the server
# --------------------------------------------------------------------------- #

class MCPServer:
    """One server bound to an inventory file and a projects file.

    Files are re-read on every tool call so mid-session edits are seen.
    ``handle_message`` is pure request-in / response-out (or ``None``
    for notifications), which is what the tests drive; ``serve`` is the
    thin stdio loop around it.
    """

    def __init__(
        self,
        inventory_path: Path,
        projects_path: Path,
        almost_threshold: int = DEFAULT_ALMOST_THRESHOLD,
    ) -> None:
        self.inventory_path = Path(inventory_path)
        self.projects_path = Path(projects_path)
        self.almost_threshold = almost_threshold

    # -- data ---------------------------------------------------------------

    def _load_inventory(self) -> Inventory:
        data = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        return parse_inventory(data)

    # -- tools --------------------------------------------------------------

    def tool_get_inventory(self, args: dict) -> str:
        inventory = self._load_inventory()
        query = str(args.get("query") or "").strip().lower()
        rows = [
            (name, quantity)
            for _, name, quantity in inventory.on_hand()
            if query in name.lower()
        ]
        total = sum(quantity for _, quantity in rows)
        header = f"{len(rows)} part type(s), {total} part(s)"
        if query:
            header += f" matching {query!r}"
        lines = [f"{header} — {self.inventory_path}"]
        lines.extend(f"  {name} x{quantity}" for name, quantity in rows)
        return "\n".join(lines)

    def tool_match_projects(self, args: dict) -> str:
        from .cli import _print_human  # deferred: cli imports are heavier

        inventory = self._load_inventory()
        projects = parse_projects(
            json.loads(self.projects_path.read_text(encoding="utf-8"))
        )
        report = match(
            inventory, projects, almost_threshold=self.almost_threshold
        )
        buffer = io.StringIO()  # no .encoding, so marks fall back to ASCII
        with contextlib.redirect_stdout(buffer):
            _print_human(report, inventory, verbose=True, color=False)
        return buffer.getvalue().rstrip()

    def tool_check_bom(self, args: dict) -> str:
        bom = args.get("bom_json")
        bom_path = args.get("bom_path")
        if bom is None and bom_path:
            path = Path(str(bom_path))
            if not path.exists():
                raise PartsMatcherError(f"no such file: {path}")
            bom = json.loads(path.read_text(encoding="utf-8"))
        if bom is None:
            raise PartsMatcherError("pass bom_path or bom_json")
        return check_bom_text(bom, self._load_inventory())

    # -- protocol -----------------------------------------------------------

    def handle_message(self, message: dict) -> "dict | None":
        """Answer one JSON-RPC message; ``None`` means nothing to send."""
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method.startswith("notifications/"):
            return None
        if msg_id is None:
            return None

        if method == "initialize":
            return self._result(msg_id, {
                "protocolVersion": params.get(
                    "protocolVersion", PROTOCOL_VERSION
                ),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            })
        if method == "ping":
            return self._result(msg_id, {})
        if method == "tools/list":
            return self._result(msg_id, {"tools": TOOLS})
        if method == "tools/call":
            return self._call_tool(msg_id, params)
        return self._error(
            msg_id, -32601, f"method not found: {method}"
        )

    def _call_tool(self, msg_id, params: dict) -> dict:
        name = params.get("name")
        handler = {
            "get_inventory": self.tool_get_inventory,
            "match_projects": self.tool_match_projects,
            "check_bom": self.tool_check_bom,
        }.get(name)
        if handler is None:
            return self._error(msg_id, -32602, f"unknown tool: {name}")
        try:
            text = handler(params.get("arguments") or {})
        except (PartsMatcherError, OSError, json.JSONDecodeError) as exc:
            # tool failures are results, not protocol errors — the model
            # should see them and recover
            return self._result(msg_id, {
                "content": [{"type": "text", "text": f"error: {exc}"}],
                "isError": True,
            })
        return self._result(msg_id, {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        })

    @staticmethod
    def _result(msg_id, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id, code: int, text: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": text},
        }

    # -- transport ----------------------------------------------------------

    def serve(self, stdin=None, stdout=None, stderr=None) -> None:
        """Run the stdio loop until EOF. Streams injectable for tests."""
        stdin = stdin if stdin is not None else sys.stdin
        stdout = stdout if stdout is not None else sys.stdout
        stderr = stderr if stderr is not None else sys.stderr
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"partsmatcher mcp: bad JSON: {exc}", file=stderr)
                continue
            try:
                response = self.handle_message(message)
            except Exception as exc:  # never let one message kill the loop
                print(f"partsmatcher mcp: {exc}", file=stderr)
                msg_id = message.get("id")
                response = (
                    self._error(msg_id, -32603, str(exc))
                    if msg_id is not None
                    else None
                )
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()
