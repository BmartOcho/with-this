"""End-to-end tests for the CLI, including the bundled sample data."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from partsmatcher import cli


def run_cli(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


def write_json(directory, filename, payload):
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


class SampleDataTests(unittest.TestCase):
    """Pin the out-of-the-box demo: all three groups populated, exact grouping."""

    def test_default_run_uses_samples_and_shows_all_groups(self):
        code, out, err = run_cli()
        self.assertEqual(code, 0)
        for header in ("BUILD NOW (3)", "ALMOST THERE (4)", "NOT YET (3)"):
            self.assertIn(header, out)
        self.assertIn("using bundled sample", err)

    def test_sample_grouping_and_sort_order(self):
        code, out, _ = run_cli("--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(
            [p["name"] for p in report["build_now"]],
            ["Blink Badge", "Reaction Timer", "Sunset Night-Light"],
        )
        self.assertEqual(
            [p["name"] for p in report["almost"]],
            [
                "LED Dice",
                "Servo Radar Sweep",
                "Ultrasonic Noise Wand",
                "Traffic Light Trainer",
            ],
        )
        self.assertEqual(
            [p["name"] for p in report["not_yet"]],
            ["Desk Weather Station", "Line-Follower Robot", "4x4x4 LED Cube"],
        )

    def test_sample_missing_detail_is_exact(self):
        code, out, _ = run_cli("--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        dice = report["almost"][0]
        self.assertEqual(dice["total_missing"], 1)
        self.assertEqual(
            dice["missing"],
            [{"name": "Red LED", "required": 7, "have": 6, "missing": 1}],
        )
        cube = report["not_yet"][2]
        self.assertEqual(cube["total_missing"], 62)
        self.assertEqual(report["summary"]["almost_threshold"], 2)
        self.assertEqual(report["summary"]["inventory_part_types"], 15)

    def test_human_output_lists_missing_parts(self):
        code, out, _ = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("needs Red LED: have 6 of 7 (short 1)", out)
        self.assertIn("needs Yellow LED: have 0 of 1 (short 1)", out)

    def test_verbose_expands_not_yet_group(self):
        code, out, _ = run_cli("--verbose")
        self.assertEqual(code, 0)
        self.assertIn("needs BME280 sensor: have 0 of 1 (short 1)", out)

    def test_raising_threshold_moves_projects_into_almost(self):
        code, out, _ = run_cli("--almost", "62", "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["not_yet"], [])
        self.assertEqual(len(report["almost"]), 7)


class OwnFilesTests(unittest.TestCase):
    def test_explicit_files_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = write_json(
                tmp, "inv.json", [{"name": "Widget", "quantity": 2}]
            )
            projects = write_json(
                tmp,
                "proj.json",
                [
                    {
                        "name": "Widget Tower",
                        "description": "Stack them high.",
                        "parts": [{"name": "widget", "quantity": 2}],
                    }
                ],
            )
            code, out, err = run_cli(inventory, projects)
        self.assertEqual(code, 0)
        self.assertIn("Widget Tower", out)
        self.assertIn("BUILD NOW (1)", out)
        self.assertNotIn("using bundled sample", err)


class ErrorHandlingTests(unittest.TestCase):
    def test_missing_file_exits_2(self):
        code, _, err = run_cli("/nonexistent/inventory.json")
        self.assertEqual(code, 2)
        self.assertIn("could not read inventory file", err)

    def test_invalid_json_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            code, _, err = run_cli(path)
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)

    def test_schema_error_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(tmp, "inv.json", [{"name": "X", "quantity": "lots"}])
            code, _, err = run_cli(path)
        self.assertEqual(code, 2)
        self.assertIn("'quantity' must be an integer", err)

    def test_negative_almost_threshold_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as ctx:
            run_cli("--almost", "-1")
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
