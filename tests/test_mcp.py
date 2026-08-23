"""Tests for the MCP server — protocol, tools, and the BOM adapter.

Everything runs in-process against temp files; no Claude, no network,
no subprocess. The stdio loop is driven with StringIO streams.
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

from partsmatcher.matcher import PartsMatcherError, parse_inventory
from partsmatcher.mcp import MCPServer, TOOLS, bom_as_project, check_bom_text

INVENTORY = {
    "parts": [
        {"name": "Arduino Uno", "quantity": 2},
        {"name": "HC-SR04 ultrasonic sensor", "quantity": 1},
        {"name": "SG90 micro servo", "quantity": 1},
        {"name": "L293D motor driver IC", "quantity": 1},
        {"name": "Burned-out LED", "quantity": 0},
    ]
}

PROJECTS = {
    "projects": [
        {
            "name": "Sonar Blinker",
            "parts": [
                {"name": "Arduino Uno", "quantity": 1},
                {"name": "HC-SR04 ultrasonic sensor", "quantity": 1},
            ],
        },
        {
            "name": "Servo Farm",
            "parts": [{"name": "SG90 micro servo", "quantity": 4}],
        },
    ]
}


def heph_bom(lines):
    return {"name": "test-design", "lines": lines}


class ServerFixture(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(self._cleanup)
        self.inventory_path = self.dir / "inventory.json"
        self.projects_path = self.dir / "projects.json"
        self.inventory_path.write_text(json.dumps(INVENTORY), encoding="utf-8")
        self.projects_path.write_text(json.dumps(PROJECTS), encoding="utf-8")
        self.server = MCPServer(self.inventory_path, self.projects_path)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, name, arguments=None, msg_id=7):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        self.assertIsNotNone(response)
        self.assertEqual(response["id"], msg_id)
        return response["result"]

    def call_text(self, name, arguments=None):
        result = self.call(name, arguments)
        self.assertFalse(result["isError"], result["content"][0]["text"])
        return result["content"][0]["text"]


class ProtocolTests(ServerFixture):
    def test_initialize_echoes_client_protocol_version(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
        )
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(
            response["result"]["serverInfo"]["name"], "partsmatcher"
        )
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_list_names_all_three_tools(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = [t["name"] for t in response["result"]["tools"]]
        self.assertEqual(
            names, ["get_inventory", "match_projects", "check_bom"]
        )

    def test_every_tool_declares_an_input_schema(self):
        for tool in TOOLS:
            self.assertEqual(tool["inputSchema"]["type"], "object", tool)
            self.assertTrue(tool["description"], tool)

    def test_notifications_get_no_response(self):
        self.assertIsNone(
            self.server.handle_message(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
        )

    def test_unknown_method_is_a_method_not_found_error(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}
        )
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_is_an_invalid_params_error(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "explode"},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_ping_pongs(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 5, "method": "ping"}
        )
        self.assertEqual(response["result"], {})


class GetInventoryTests(ServerFixture):
    def test_lists_parts_on_hand_with_totals(self):
        text = self.call_text("get_inventory")
        self.assertIn("4 part type(s), 5 part(s)", text)
        self.assertIn("Arduino Uno x2", text)

    def test_zero_quantity_entries_are_not_listed(self):
        text = self.call_text("get_inventory")
        self.assertNotIn("Burned-out LED", text)

    def test_query_filters_case_insensitively(self):
        text = self.call_text("get_inventory", {"query": "SERVO"})
        self.assertIn("1 part type(s), 1 part(s) matching 'servo'", text)
        self.assertIn("SG90 micro servo x1", text)
        self.assertNotIn("Arduino Uno", text)


class MatchProjectsTests(ServerFixture):
    def test_produces_the_canonical_three_bucket_report(self):
        text = self.call_text("match_projects")
        self.assertIn("BUILD NOW (1)", text)
        self.assertIn("Sonar Blinker", text)
        self.assertIn("NOT YET (1)", text)
        self.assertIn("Servo Farm", text)

    def test_report_uses_ascii_marks_never_ansi_codes(self):
        text = self.call_text("match_projects")
        self.assertIn("[OK]", text)
        self.assertNotIn("\x1b[", text)

    def test_rereads_the_inventory_file_on_every_call(self):
        before = self.call_text("match_projects")
        self.assertIn("NOT YET (1)", before)
        richer = json.loads(json.dumps(INVENTORY))
        richer["parts"][2]["quantity"] = 4  # SG90 1 -> 4
        self.inventory_path.write_text(json.dumps(richer), encoding="utf-8")
        after = self.call_text("match_projects")
        self.assertIn("BUILD NOW (2)", after)


class BomAdapterTests(unittest.TestCase):
    def setUp(self):
        self.inventory = parse_inventory(INVENTORY)
        self.known = set(self.inventory.quantities)

    def test_prefers_the_spelling_the_inventory_knows(self):
        project = bom_as_project(
            heph_bom(
                [{"key": "Arduino Uno", "description": "Arduino Uno R3 main board", "qty": 1}]
            ),
            self.known,
        )
        self.assertEqual(project["parts"], [{"name": "Arduino Uno", "quantity": 1}])

    def test_description_wins_when_neither_spelling_is_known(self):
        project = bom_as_project(
            heph_bom([{"key": "l298n", "description": "L298N motor driver", "qty": 1}]),
            self.known,
        )
        self.assertEqual(project["parts"][0]["name"], "L298N motor driver")

    def test_key_is_used_when_description_is_absent(self):
        project = bom_as_project(
            heph_bom([{"key": "6 mm steel dowel", "qty": 3}]), self.known
        )
        self.assertEqual(
            project["parts"], [{"name": "6 mm steel dowel", "quantity": 3}]
        )

    def test_zero_quantity_and_nameless_lines_are_dropped(self):
        project = bom_as_project(
            heph_bom(
                [
                    {"key": "ghost", "qty": 0},
                    {"qty": 5},
                    {"key": "real part", "qty": 1},
                ]
            ),
            self.known,
        )
        self.assertEqual(len(project["parts"]), 1)

    def test_a_bom_with_no_usable_lines_raises(self):
        with self.assertRaises(PartsMatcherError):
            bom_as_project(heph_bom([{"key": "ghost", "qty": 0}]), self.known)

    def test_not_a_bom_raises(self):
        with self.assertRaises(PartsMatcherError):
            bom_as_project({"parts": []}, self.known)


class CheckBomTests(ServerFixture):
    def test_fully_owned_bom_is_build_now(self):
        text = self.call_text(
            "check_bom",
            {
                "bom_json": heph_bom(
                    [{"key": "arduino_uno", "description": "Arduino Uno", "qty": 1}]
                )
            },
        )
        self.assertIn("Verdict: BUILD NOW", text)
        self.assertIn("[OK] Arduino Uno x1", text)

    def test_short_line_reports_have_and_buy_counts(self):
        text = self.call_text(
            "check_bom",
            {
                "bom_json": heph_bom(
                    [{"description": "SG90 micro servo", "qty": 3}]
                )
            },
        )
        self.assertIn("SG90 micro servo: have 1 of 3 (buy 2)", text)

    def test_not_owned_line_carries_a_closest_name_hint(self):
        text = self.call_text(
            "check_bom",
            {
                "bom_json": heph_bom(
                    [{"description": "L298N motor driver", "qty": 1}]
                )
            },
        )
        self.assertIn("[X] L298N motor driver x1", text)
        self.assertIn("L293D motor driver IC", text)
        self.assertIn("not a match", text)

    def test_reads_a_bom_from_a_file_path(self):
        bom_path = self.dir / "bom.json"
        bom_path.write_text(
            json.dumps(
                heph_bom([{"description": "Arduino Uno", "qty": 2}])
            ),
            encoding="utf-8",
        )
        text = self.call_text("check_bom", {"bom_path": str(bom_path)})
        self.assertIn("Verdict: BUILD NOW", text)

    def test_missing_file_is_a_tool_error_not_a_crash(self):
        result = self.call("check_bom", {"bom_path": str(self.dir / "no.json")})
        self.assertTrue(result["isError"])
        self.assertIn("no such file", result["content"][0]["text"])

    def test_no_arguments_is_a_tool_error(self):
        result = self.call("check_bom", {})
        self.assertTrue(result["isError"])
        self.assertIn("bom_path or bom_json", result["content"][0]["text"])

    def test_malformed_bom_is_a_tool_error(self):
        result = self.call("check_bom", {"bom_json": {"nope": True}})
        self.assertTrue(result["isError"])

    def test_verdict_text_is_pure_and_deterministic(self):
        inventory = parse_inventory(INVENTORY)
        bom = heph_bom([{"description": "Arduino Uno", "qty": 1}])
        self.assertEqual(
            check_bom_text(bom, inventory), check_bom_text(bom, inventory)
        )


class ServeLoopTests(ServerFixture):
    def run_lines(self, *lines):
        stdin = io.StringIO("".join(line + "\n" for line in lines))
        stdout, stderr = io.StringIO(), io.StringIO()
        self.server.serve(stdin=stdin, stdout=stdout, stderr=stderr)
        responses = [
            json.loads(line)
            for line in stdout.getvalue().splitlines()
            if line
        ]
        return responses, stderr.getvalue()

    def test_a_session_over_stdio_end_to_end(self):
        responses, stderr = self.run_lines(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                }
            ),
            json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            ),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_inventory",
                        "arguments": {"query": "uno"},
                    },
                }
            ),
        )
        self.assertEqual(stderr, "")
        self.assertEqual([r["id"] for r in responses], [1, 2, 3])
        self.assertIn(
            "Arduino Uno x2", responses[2]["result"]["content"][0]["text"]
        )

    def test_bad_json_is_skipped_with_a_note_and_the_loop_survives(self):
        responses, stderr = self.run_lines(
            "this is not json",
            json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}),
        )
        self.assertIn("bad JSON", stderr)
        self.assertEqual([r["id"] for r in responses], [9])

    def test_blank_lines_are_ignored(self):
        responses, stderr = self.run_lines(
            "", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}), ""
        )
        self.assertEqual(len(responses), 1)


if __name__ == "__main__":
    unittest.main()
