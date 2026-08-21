# Gates: Inventory zero-quantity accounting

Scope: `Inventory.distinct_parts` counts part types with quantity 0 as parts on
hand, disagreeing with `total_units` (which excludes them). Make the two
consistent without changing lookup, matching, or alias behavior.

Depth Tree (3):
  L1  Correct zero-quantity accounting in Inventory
  L2.1  Core semantics      -> G1, G2, G7
  L2.2  Behavior preserved  -> G3, G5
  L2.3  Coverage and sweep  -> G4, G6

- [x] G1: distinct_parts counts only part types actually on hand (quantity > 0), while total_units is unchanged.
  CHECK: python3 -c 'from partsmatcher.matcher import parse_inventory as p; i=p([{"name":"Servo","quantity":0},{"name":"LED","quantity":5}]); print("distinct_parts=%d total_units=%d" % (i.distinct_parts, i.total_units))'
  EXPECT: distinct_parts=1 total_units=5
  EVIDENCE: distinct_parts=1 total_units=5

- [x] G2: A zero-quantity entry is still retained in the inventory: its key stays in quantities, have() returns 0, and its display spelling survives.
  CHECK: python3 -c 'from partsmatcher.matcher import parse_inventory as p; i=p([{"name":"Servo  Motor","quantity":0}]); print("have=%d key=%s display=%s" % (i.have("servo motor"), "servo motor" in i.quantities, i.display_names.get("servo motor")))'
  EXPECT: have=0 key=True display=Servo Motor
  EVIDENCE: have=0 key=True display=Servo Motor

- [x] G3: Matching is unaffected: a project needing a zero-quantity part still reports required/have/missing correctly and lands in the same bucket as before the change.
  CHECK: python3 -c 'from partsmatcher.matcher import parse_inventory as pi, parse_projects as pp, match; i=pi([{"name":"Servo","quantity":0},{"name":"LED","quantity":5}]); pr=pp([{"name":"Spinner","parts":[{"name":"Servo","quantity":1}]}]); r=match(i,pr); b="build_now" if r.build_now else ("almost" if r.almost else "not_yet"); m=(r.almost or r.not_yet or r.build_now)[0].missing[0]; print("bucket=%s required=%d have=%d missing=%d" % (b, m.required, m.have, m.missing))'
  EXPECT: bucket=almost required=1 have=0 missing=1
  EVIDENCE: bucket=almost required=1 have=0 missing=1

- [x] G4: Named regression tests for zero-quantity accounting exist in tests/test_matcher.py and pass.
  CHECK: echo "new_tests_passing=$(python3 -m unittest tests.test_matcher -v 2>&1 | grep -cE 'test_(zero_quantity_entry|zero_quantity_merges|zero_quantity_part|on_hand_preserves).*\.\.\. ok')"
  EXPECT: new_tests_passing=5
  EVIDENCE: new_tests_passing=5

- [x] G5: The full suite passes with no test lost (baseline before this change: 151 tests, OK).
  CHECK: python3 -m unittest discover 2>&1 | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' '
  EXPECT: /Ran 15[1-9] tests.*OK/
  EVIDENCE: Ran 156 tests in 4.669s OK

- [x] G6: Every other reader of distinct_parts / quantities in the package is audited for the same zero-quantity assumption, and each is either correct already or fixed. Manual gate: evidence must list every call site as file:line with a verdict.
  EVIDENCE: 13 distinct call sites swept (22 grep hits incl. paired total_units lines); 3 were defective and are fixed, 10 correct. FIXED: matcher.py:109-113 distinct_parts (the defect; now counts quantity>0); chat.py:148 render loop and app/server.py:89 sidebar payload (both emitted a x0 row; now iterate on_hand()). CORRECT AS-IS: matcher.py:93 have() (0 and absent are rightly identical for lookup); matcher.py:117 total_units (a 0 term adds nothing); matcher.py:247 evaluate() (have=0 yields the right deficit). Pure consumers of the corrected count, fixed transitively: cli.py:343, cli.py:368, app/__init__.py:180, app/server.py:85, chat.py:152, chat.py:439, chat.py:1077.

- [x] G7: The Inventory docstring states the zero-quantity semantics, so the next reader does not re-derive them.
  CHECK: grep -c "quantity 0\|zero-quantity" partsmatcher/matcher.py
  EXPECT: /^[1-9]/
  EVIDENCE: 1

- [x] G8: Added by the G6 sweep. The rendered inventory surfaces list only parts on hand, so a zero-quantity entry never appears as "×0" and the rendered row count agrees with distinct_parts. Covers the chat context (chat.py) and the app sidebar payload (app/server.py) through one shared accessor.
  CHECK: python3 -c 'from partsmatcher.matcher import parse_inventory as p; from partsmatcher.chat import build_context_markdown as b; i=p([{"name":"Servo","quantity":0},{"name":"LED","quantity":5}]); t=b(i,None); print("rows=%d count=%d servo_shown=%s led_shown=%s" % (len(i.on_hand()), i.distinct_parts, "Servo" in t, "- LED x5".replace("x","×") in t))'
  EXPECT: rows=1 count=1 servo_shown=False led_shown=True
  EVIDENCE: rows=1 count=1 servo_shown=False led_shown=True
