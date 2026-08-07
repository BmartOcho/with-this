"""Unit tests for the core matching logic."""

import unittest

from partsmatcher import (
    PartsMatcherError,
    match,
    normalize_name,
    parse_inventory,
    parse_projects,
)


def make_inventory(*pairs):
    return parse_inventory([{"name": name, "quantity": qty} for name, qty in pairs])


def project_dict(name, *pairs, description=""):
    return {
        "name": name,
        "description": description,
        "parts": [{"name": part, "quantity": qty} for part, qty in pairs],
    }


class NormalizationTests(unittest.TestCase):
    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(normalize_name("  Red   LED "), "red led")
        self.assertEqual(normalize_name("RED LED"), normalize_name("red led"))

    def test_matching_ignores_case_and_spacing(self):
        inventory = make_inventory(("Red LED", 3))
        projects = parse_projects([project_dict("P", ("  red   led ", 3))])
        report = match(inventory, projects)
        self.assertEqual(len(report.build_now), 1)


class InventoryParsingTests(unittest.TestCase):
    def test_duplicate_names_merge_by_summing(self):
        inventory = parse_inventory(
            [
                {"name": "Red LED", "quantity": 2},
                {"name": "red led", "quantity": 3},
            ]
        )
        self.assertEqual(inventory.have("Red LED"), 5)
        self.assertEqual(inventory.distinct_parts, 1)

    def test_quantity_defaults_to_one(self):
        inventory = parse_inventory([{"name": "Red LED"}, {"name": "Red LED"}])
        self.assertEqual(inventory.have("red led"), 2)

    def test_wrapped_and_bare_forms_are_equivalent(self):
        bare = parse_inventory([{"name": "Nut", "quantity": 4}])
        wrapped = parse_inventory({"parts": [{"name": "Nut", "quantity": 4}]})
        self.assertEqual(bare.quantities, wrapped.quantities)

    def test_extra_fields_are_tolerated(self):
        inventory = parse_inventory(
            {
                "parts": [
                    {
                        "name": "Red LED",
                        "quantity": 2,
                        "source": "vision",
                        "confidence": 0.93,
                        "bin": "A4",
                    }
                ],
                "captured_at": "2026-08-06T12:00:00Z",
            }
        )
        self.assertEqual(inventory.have("Red LED"), 2)

    def test_rejects_non_integer_quantity(self):
        for bad in ("2", 2.5, True, None):
            with self.assertRaises(PartsMatcherError):
                parse_inventory([{"name": "X", "quantity": bad}])

    def test_rejects_negative_quantity_and_missing_name(self):
        with self.assertRaises(PartsMatcherError):
            parse_inventory([{"name": "X", "quantity": -1}])
        with self.assertRaises(PartsMatcherError):
            parse_inventory([{"quantity": 3}])
        with self.assertRaises(PartsMatcherError):
            parse_inventory([{"name": "   ", "quantity": 3}])

    def test_rejects_wrong_top_level_shapes(self):
        with self.assertRaises(PartsMatcherError):
            parse_inventory("not a list")
        with self.assertRaises(PartsMatcherError):
            parse_inventory({"stuff": []})


class ProjectParsingTests(unittest.TestCase):
    def test_required_parts_alias(self):
        projects = parse_projects(
            [{"name": "P", "required_parts": [{"name": "Nut", "quantity": 1}]}]
        )
        self.assertEqual(projects[0].requirements, {"nut": 1})

    def test_duplicate_requirements_merge(self):
        projects = parse_projects(
            [project_dict("P", ("Red LED", 2), ("red led", 3))]
        )
        self.assertEqual(projects[0].requirements, {"red led": 5})

    def test_rejects_project_without_parts(self):
        with self.assertRaises(PartsMatcherError):
            parse_projects([{"name": "P"}])
        with self.assertRaises(PartsMatcherError):
            parse_projects([{"name": "P", "parts": []}])

    def test_rejects_zero_quantity_requirement(self):
        with self.assertRaises(PartsMatcherError):
            parse_projects([project_dict("P", ("Nut", 0))])

    def test_description_is_optional(self):
        projects = parse_projects([{"name": "P", "parts": [{"name": "Nut"}]}])
        self.assertEqual(projects[0].description, "")


class MatchingTests(unittest.TestCase):
    def test_exact_quantities_are_buildable(self):
        inventory = make_inventory(("LED", 3), ("Resistor", 1))
        projects = parse_projects([project_dict("P", ("LED", 3), ("Resistor", 1))])
        report = match(inventory, projects)
        self.assertEqual([m.name for m in report.build_now], ["P"])
        self.assertEqual(report.almost, [])
        self.assertEqual(report.not_yet, [])

    def test_partial_quantity_counts_missing_units(self):
        # Needs 3 LEDs, owns 2 -> that counts as missing 1.
        inventory = make_inventory(("LED", 2))
        projects = parse_projects([project_dict("P", ("LED", 3))])
        report = match(inventory, projects)
        self.assertEqual(len(report.almost), 1)
        result = report.almost[0]
        self.assertEqual(result.total_missing, 1)
        part = result.missing[0]
        self.assertEqual((part.name, part.required, part.have, part.missing), ("LED", 3, 2, 1))

    def test_unknown_part_counts_from_zero(self):
        inventory = make_inventory(("LED", 5))
        projects = parse_projects([project_dict("P", ("Servo", 2))])
        report = match(inventory, projects)
        self.assertEqual(report.almost[0].missing[0].have, 0)
        self.assertEqual(report.almost[0].total_missing, 2)

    def test_threshold_boundary_at_two_and_three(self):
        inventory = make_inventory(("LED", 0))
        two_short = parse_projects([project_dict("Two", ("LED", 2))])
        three_short = parse_projects([project_dict("Three", ("LED", 3))])
        self.assertEqual(len(match(inventory, two_short).almost), 1)
        self.assertEqual(len(match(inventory, three_short).not_yet), 1)

    def test_missing_units_sum_across_part_types(self):
        # Three different parts short one unit each = 3 missing -> NOT YET.
        inventory = make_inventory(("A", 0), ("B", 0), ("C", 0))
        projects = parse_projects([project_dict("P", ("A", 1), ("B", 1), ("C", 1))])
        report = match(inventory, projects)
        self.assertEqual(len(report.not_yet), 1)
        self.assertEqual(report.not_yet[0].total_missing, 3)
        self.assertEqual(report.not_yet[0].missing_kinds, 3)

    def test_custom_threshold(self):
        inventory = make_inventory(("LED", 0))
        projects = parse_projects([project_dict("P", ("LED", 5))])
        self.assertEqual(len(match(inventory, projects, almost_threshold=5).almost), 1)
        self.assertEqual(len(match(inventory, projects, almost_threshold=0).not_yet), 1)
        with self.assertRaises(ValueError):
            match(inventory, projects, almost_threshold=-1)

    def test_almost_sorted_by_fewest_missing_then_kinds_then_name(self):
        inventory = make_inventory(("A", 0), ("B", 0))
        projects = parse_projects(
            [
                # 2 units missing across 2 kinds
                project_dict("Zeta", ("A", 1), ("B", 1)),
                # 2 units missing across 1 kind -> sorts before Zeta
                project_dict("Yankee", ("A", 2)),
                # 1 unit missing -> sorts first
                project_dict("alpha", ("A", 1)),
                # 1 unit missing, ties with alpha -> name order (case-insensitive)
                project_dict("Beta", ("B", 1)),
            ]
        )
        report = match(inventory, projects)
        self.assertEqual(
            [m.name for m in report.almost], ["alpha", "Beta", "Yankee", "Zeta"]
        )

    def test_build_now_sorted_by_name(self):
        inventory = make_inventory(("A", 10))
        projects = parse_projects(
            [project_dict("bravo", ("A", 1)), project_dict("Alpha", ("A", 1))]
        )
        report = match(inventory, projects)
        self.assertEqual([m.name for m in report.build_now], ["Alpha", "bravo"])

    def test_projects_do_not_consume_inventory(self):
        # Two projects each need the single servo; both count as buildable.
        inventory = make_inventory(("Servo", 1))
        projects = parse_projects(
            [project_dict("One", ("Servo", 1)), project_dict("Two", ("Servo", 1))]
        )
        report = match(inventory, projects)
        self.assertEqual(len(report.build_now), 2)


if __name__ == "__main__":
    unittest.main()
