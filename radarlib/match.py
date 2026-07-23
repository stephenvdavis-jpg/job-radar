"""Pay parsing, location filtering, and fit scoring for the job radar.

Tuning lives here: keyword lists and the town allowlist are meant to be edited
as the radar's judgment gets calibrated against real digests.
"""

import re

MIN_HOURLY = 25.0
MIN_ANNUAL = 52_000.0
FULL_TIME_HOURS = 2080  # used to convert annual salaries to an hourly figure

# Towns within roughly a 30-minute commute of the Burlington core.
COMMUTABLE_TOWNS = {
    "burlington", "south burlington", "winooski", "colchester", "essex",
    "essex junction", "essex jct", "williston", "shelburne", "charlotte",
    "hinesburg", "jericho", "richmond", "milton", "st. george", "saint george",
    "underhill",
    "waterbury",  # ~35 min, kept for Ben & Jerry's / state satellite offices
}
REMOTE_HINTS = ("remote", "work from home", "telework", "virtual")

# --- Fit keywords -----------------------------------------------------------
# Strong: squarely in the healthcare-administration / MHA lane.
STRONG_KEYWORDS = (
    "healthcare administr", "health administr", "practice manager",
    "practice coordinator", "patient access", "patient services",
    "patient experience", "clinic coordinator", "clinical coordinator",
    "care coordinator", "care manager", "program coordinator",
    "program manager", "project coordinator", "quality improvement",
    "quality coordinator", "revenue cycle", "population health",
    "health information", "medical office", "office coordinator",
    "practice supervisor", "patient scheduling", "referral coordinator",
    "utilization", "credentialing", "health services", "community health",
    "public health", "mental health program", "operations coordinator",
    "administrative coordinator", "admissions coordinator",
)
# Good: broader business/admin roles that fit her degrees.
GOOD_KEYWORDS = (
    "coordinator", "administrator", "administrative", "operations",
    "office manager", "executive assistant", "program assistant",
    "program associate", "analyst",
    "specialist", "scheduler", "registrar", "billing", "human resources",
    "outreach", "enrollment", "member services", "case manager", "supervisor",
    "assistant manager", "compliance",
)
# Hard exclusions: roles needing licenses/degrees she doesn't have, or
# obviously out-of-lane work.
EXCLUDE_KEYWORDS = (
    "registered nurse", " rn ", "rn,", "rn -", "(rn)", "physician", " md ",
    "nurse", "aprn", "psychiatrist", "psychologist", "therapist",
    "clinician", "licensed clinical", "residential counselor", "camp counselor",
    "school counselor", "guidance counselor", "licensed counselor",
    "social worker", "lcsw", "lpn", "lna", "paramedic", "emt",
    "pharmacist", "pharmacy technician", "radiolog", "sonograph", "surgical",
    "dental", "dentist", "physical therap", "occupational therap",
    "speech language", "phlebotom", "respiratory therap", "faculty",
    "professor", "postdoc", "adjunct", "software", "engineer", "developer",
    "scientist", "custodian", "janitor", "housekeep", "dishwasher", "cook",
    "chef", "driver", "cdl", "mechanic", "electrician", "plumber", "welder",
    "security officer", "police", "trooper", "sheriff", "correctional",
    "game warden", "firefighter", "military", "maintenance", "groundskeeper",
    "attorney", "paralegal",
    "intern ", "internship", "per diem", "travel nurse", "locum",
)
# Softly senior: probably needs 10+ years, but still "worth a look".
SENIOR_HINTS = ("director", "chief", "vice president", " vp ", "senior manager", "head of")

# Money amount: $60,000 / $26.50 / $60k. Group 1 = number, group 2 = k-suffix.
_MONEY = r"\$\s*([\d,]+(?:\.\d+)?)\s*([kK])?"
# Optional unit wording that may follow the FIRST endpoint of a range
# ("$20/hour - $30/hour", "$52,000 per year to $62,000 per year").
_UNIT = r"(?:\s*(?:/\s*(?:hour|hr|year|yr)|per\s+(?:hour|year)|hourly|annually))?"
_RANGE = rf"{_MONEY}{_UNIT}\s*(?:-|–|—|to)\s*{_MONEY}"

PAY_WORDS = ("salary", "pay", "compensation", "wage", "rate", "hour", "/hr",
             "hourly", "per year", "/yr", "annual", "starting at")
FEE_WORDS = ("fee", "bonus", "deposit", "stipend", "reimburs", "allowance",
             "grant", "budget", "million", "tuition")


def _to_float(num: str, k_suffix: str | None) -> float:
    val = float(num.replace(",", ""))
    return val * 1000 if k_suffix else val


def parse_pay(text: str) -> tuple[float | None, float | None, str | None]:
    """Extract (min_hourly, max_hourly, raw_snippet) from posting text.

    Annual figures are normalized to hourly so everything compares against
    the $25/hr floor. Returns (None, None, None) when no pay is found.
    """
    if not text:
        return None, None, None
    text = text.replace(" ", " ")

    def classify(lo: float, hi: float, context: str) -> tuple[float, float] | None:
        hourly_ctx = any(w in context for w in ("hour", "/hr", "hr.", "hourly"))
        annual_ctx = any(w in context for w in ("year", "/yr", "annual", "salary"))
        if hi < 250 and (hourly_ctx or not annual_ctx):
            got = (lo, hi)  # dollars/hour
        elif hi >= 1000:
            got = (lo / FULL_TIME_HOURS, hi / FULL_TIME_HOURS)  # dollars/year
        else:
            return None
        # Plausibility bounds: job pay, not grant budgets or fee amounts.
        if not (7.0 <= got[1] <= 150.0) or got[0] < 5.0:
            return None
        return got

    def fee_nearby(start: int, end: int) -> bool:
        near = text[max(0, start - 12): end + 10].lower()
        return any(w in near for w in FEE_WORDS)

    # Collect candidates and prefer: ranges over single figures, then amounts
    # near pay words, then the earliest mention (a page's own pay field comes
    # before dollar figures buried in a description).
    candidates: list[tuple[int, int, tuple[float, float, str]]] = []
    range_spans: list[tuple[int, int]] = []
    for m in re.finditer(_RANGE, text):
        lo, hi = sorted((_to_float(m.group(1), m.group(2)),
                         _to_float(m.group(3), m.group(4))))
        range_spans.append(m.span())
        if fee_nearby(m.start(), m.end()):
            continue
        context = text[max(0, m.start() - 50): m.end() + 50].lower()
        got = classify(lo, hi, context)
        if got:
            rank = 2 + (2 if any(w in context for w in PAY_WORDS) else 0)
            candidates.append((-rank, m.start(), (got[0], got[1], m.group(0).strip())))
    for m in re.finditer(_MONEY, text):
        if any(s <= m.start() < e for s, e in range_spans):
            continue  # already part of a range
        if fee_nearby(m.start(), m.end()):
            continue
        val = _to_float(m.group(1), m.group(2))
        context = text[max(0, m.start() - 50): m.end() + 50].lower()
        got = classify(val, val, context)
        if got:
            rank = 2 if any(w in context for w in PAY_WORDS) else 0
            candidates.append((-rank, m.start(), (got[0], got[1], m.group(0).strip())))
    if not candidates:
        return None, None, None
    _, _, (lo, hi, raw) = min(candidates)
    return round(lo, 2), round(hi, 2), raw


# Two-letter codes of every state except Vermont, to catch "Charlotte, NC".
_NON_VT_STATE = re.compile(
    r",\s*(a[klrsz]|c[aot]|d[ce]|fl|ga|hi|i[adln]|k[sy]|la|m[adeinost]|"
    r"n[cdehjmvy]|o[hkr]|pa|ri|s[cd]|t[nx]|ut|va|w[aivy])\b", re.I)


def location_ok(location: str, remote: bool) -> bool:
    if remote:
        return True
    loc = (location or "").lower()
    if any(hint in loc for hint in REMOTE_HINTS):
        return True
    if _NON_VT_STATE.search(loc) and "vt" not in loc and "vermont" not in loc:
        return False  # explicitly somewhere else ("Burlington, MA")
    return any(town in loc for town in COMMUTABLE_TOWNS)


def score_job(title: str, location: str, remote: bool,
              pay_min_hr: float | None, pay_max_hr: float | None,
              description: str = "", location_exempt: bool = False,
              desc_healthcare: bool = False) -> tuple[str, float, list[str]]:
    """Return (tier, score, reasons). Tiers: 'best', 'look', 'skip'.

    location_exempt: employer is hybrid/remote-friendly enough that we don't
    filter on the office's town (e.g. BCBSVT in Berlin).
    desc_healthcare: carry-over signal that an earlier run's detail fetch saw
    clinical context in the description (descriptions aren't stored).
    """
    t = f" {title.lower()} "
    reasons: list[str] = []

    if not location_exempt and not location_ok(location, remote):
        return "skip", 0.0, [f"outside commute range ({location})"]

    for kw in EXCLUDE_KEYWORDS:
        if kw in t:
            return "skip", 0.0, [f"role mismatch ({kw.strip()})"]

    score = 0.0
    if any(kw in t for kw in STRONG_KEYWORDS):
        score += 3.0
        reasons.append("healthcare-admin fit")
    elif any(kw in t for kw in GOOD_KEYWORDS):
        score += 1.5
        reasons.append("business/admin fit")
    else:
        reasons.append("title outside target keywords")

    # Benefits blurbs say "healthcare coverage" everywhere, so require words
    # that only appear when the employer actually does healthcare work.
    desc = description.lower()
    if desc_healthcare or (desc and any(
            kw in desc for kw in ("hospital", "clinic", "patient",
                                  "public health", "mental health"))):
        score += 0.5

    if any(kw in t for kw in SENIOR_HINTS):
        score -= 1.0
        reasons.append("likely senior-level")

    # Pay checks against the $25/hr (~$52k/yr) floor.
    if pay_max_hr is not None and pay_max_hr < MIN_HOURLY:
        return "skip", score, reasons + [f"pay tops out under $25/hr (${pay_max_hr}/hr)"]
    straddles_floor = (pay_min_hr is not None and pay_min_hr < MIN_HOURLY
                       and pay_max_hr is not None and pay_max_hr >= MIN_HOURLY)
    if pay_min_hr is not None and pay_min_hr >= MIN_HOURLY:
        score += 1.0
        reasons.append("meets pay floor")
    elif straddles_floor:
        reasons.append(f"pay range starts under $25/hr (${pay_min_hr}/hr)")
    elif pay_min_hr is None:
        score -= 0.25
        reasons.append("pay not listed")

    if score >= 2.75:
        # A range that starts below the floor is never a confident best match.
        return ("look" if straddles_floor else "best"), score, reasons
    if score >= 1.0:
        return "look", score, reasons
    return "skip", score, reasons


def desc_has_healthcare(description: str) -> bool:
    """Persistable one-bit summary of a fetched description (see score_job)."""
    desc = (description or "").lower()
    return any(kw in desc for kw in ("hospital", "clinic", "patient",
                                     "public health", "mental health"))
