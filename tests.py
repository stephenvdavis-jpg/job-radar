#!/usr/bin/env python3
"""Quick sanity tests: python3 tests.py — prints PASS/FAIL lines, exits 1 on failure."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from radarlib.match import location_ok, parse_pay, score_job  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS " if ok else "FAIL ") + name, detail)
    if not ok:
        failures += 1


PAY_CASES = [
    ("$20/hour - $30/hour", (20.0, 30.0)),
    ("$52,000/year - $62,000/year", (25.0, 29.81)),
    ("$25/hr to $30/hr", (25.0, 30.0)),
    ("$60k-$70k", (28.85, 33.65)),
    ("$26 - $32 per hour", (26.0, 32.0)),
    ("$58,406.40 - $65,062.40 Annually", (28.08, 31.28)),
    ("Salary $195,053,740.44 grant. hourly rate $26.50 per hour", (26.5, 26.5)),
    ("Grant budget: $75,000-$100,000. Compensation: $60,000 annually", (28.85, 28.85)),
    ("application fee of $50 required", (None, None)),
    ("no pay mentioned", (None, None)),
]
for text, want in PAY_CASES:
    lo, hi, _ = parse_pay(text)
    ok = ((lo is None and want[0] is None) or
          (lo is not None and want[0] is not None
           and abs(lo - want[0]) < 0.05 and abs(hi - want[1]) < 0.05))
    check(f"parse_pay: {text[:44]!r}", ok, f"-> ({lo}, {hi})")

LOC_CASES = [
    ("Burlington, VT", True), ("Burlington, MA", False),
    ("Charlotte, NC", False), ("Richmond, VA", False),
    ("Colchester, Vermont", True), ("Remote", True),
    ("Schenectady, NY", False), ("Essex Jct, Vermont", True),
    ("Waterbury, VT", True), ("Montpelier, VT", False),
]
for loc, want in LOC_CASES:
    check(f"location_ok: {loc!r}", location_ok(loc, remote=False) == want)

tier, _, _ = score_job("Practice Manager", "Burlington, VT", False, 30.0, 35.0)
check("strong fit + pay -> best", tier == "best")
tier, _, _ = score_job("Practice Manager", "Burlington, VT", False, 20.0, 30.0)
check("pay straddling $25 floor caps at look", tier == "look")
tier, _, _ = score_job("Registered Nurse", "Burlington, VT", False, 40.0, 50.0)
check("licensed role excluded", tier == "skip")
tier, _, _ = score_job("Program Coordinator", "Boston, MA", False, None, None)
check("out-of-state skipped", tier == "skip")
tier, _, _ = score_job("Operations Specialist", "Berlin, VT", False, 30.0, 35.0,
                       location_exempt=True)
check("location-exempt employer passes", tier in ("best", "look"))

sys.exit(1 if failures else 0)
