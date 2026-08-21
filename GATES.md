# Gates: MatchReport.total_projects

Scope: cli.py derives the total project count with the same inline sum
`len(build_now) + len(almost) + len(not_yet)` in two places. Move it onto
MatchReport as a property, with byte-identical CLI output.

Depth Tree (3):
  L1  Give the report its own total, used everywhere
  L2.1  Core property        -> G1, G2
  L2.2  Call sites converted -> G3, G4
  L2.3  Output unchanged     -> G5, G6, G7

- [x] G1: MatchReport exposes total_projects, equal to the sum of the three buckets.
  CHECK: python3 -c 'from partsmatcher.matcher import parse_inventory as pi, parse_projects as pp, match; i=pi([{"name":"LED","quantity":5}]); pr=pp([{"name":"A","parts":[{"name":"LED","quantity":1}]},{"name":"B","parts":[{"name":"Servo","quantity":9}]}]); r=match(i,pr); print("total=%d sum=%d" % (r.total_projects, len(r.build_now)+len(r.almost)+len(r.not_yet)))'
  EXPECT: total=2 sum=2
  EVIDENCE: total=2 sum=2

- [x] G2: total_projects is 0 for an empty project list (no crash, no special-casing needed at call sites).
  CHECK: python3 -c 'from partsmatcher.matcher import Inventory, match; print("empty_total=%d" % match(Inventory(quantities={}, display_names={}), []).total_projects)'
  EXPECT: empty_total=0
  EVIDENCE: empty_total=0

- [x] G3: No *duplicated* inline three-bucket sum survives at any call site; matcher.py's property body is the single definition.
  CHECK: echo "inline_sums=$(grep -rc 'len(report.build_now) + len(report.almost)' partsmatcher/ | grep -v ':0$' | wc -l | tr -d ' ')"
  EXPECT: inline_sums=0
  EVIDENCE: inline_sums=0

- [x] G4: Both former call sites now read the property.
  CHECK: echo "uses=$(grep -rc 'report.total_projects' partsmatcher/cli.py | tr -d ' ')"
  EXPECT: uses=2
  EVIDENCE: uses=2

- [x] G5: Human CLI output on the bundled samples is byte-identical to the pre-change baseline.
  CHECK: python3 -m partsmatcher > /tmp/claude-0/-home-user-with-this/124c4a5f-acdb-57f0-8451-5024d426ba3c/scratchpad/human_after.txt 2>&1; diff -q /tmp/claude-0/-home-user-with-this/124c4a5f-acdb-57f0-8451-5024d426ba3c/scratchpad/human_before.txt /tmp/claude-0/-home-user-with-this/124c4a5f-acdb-57f0-8451-5024d426ba3c/scratchpad/human_after.txt >/dev/null && echo human_identical=yes || echo human_identical=no
  EXPECT: human_identical=yes
  EVIDENCE: human_identical=yes

- [x] G6: JSON CLI output on the bundled samples is byte-identical to the pre-change baseline.
  CHECK: python3 -m partsmatcher --json > /tmp/claude-0/-home-user-with-this/124c4a5f-acdb-57f0-8451-5024d426ba3c/scratchpad/json_after.txt 2>&1; diff -q /tmp/claude-0/-home-user-with-this/124c4a5f-acdb-57f0-8451-5024d426ba3c/scratchpad/json_before.txt /tmp/claude-0/-home-user-with-this/124c4a5f-acdb-57f0-8451-5024d426ba3c/scratchpad/json_after.txt >/dev/null && echo json_identical=yes || echo json_identical=no
  EXPECT: json_identical=yes
  EVIDENCE: json_identical=yes

- [x] G7: The full suite passes with no test lost (baseline before this change: 156 tests, OK), including a named regression test for total_projects.
  CHECK: python3 -m unittest discover 2>&1 | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' '
  EXPECT: /Ran 15[7-9] tests.*OK/
  EVIDENCE: Ran 158 tests in 4.725s OK

- [x] G8: A named test covers total_projects and passes.
  CHECK: echo "new_tests_passing=$(python3 -m unittest tests.test_matcher -v 2>&1 | grep -cE 'test_total_projects.*\.\.\. ok')"
  EXPECT: new_tests_passing=2
  EVIDENCE: new_tests_passing=2
