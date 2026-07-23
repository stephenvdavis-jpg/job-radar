#!/usr/bin/env python3
"""Burlington-area job radar.

Usage:
    python3 radar.py run          # fetch all sources, update DB, write digest
    python3 radar.py run --open   # same, then open the digest in the browser
    python3 radar.py sources      # list configured sources and their status
    python3 radar.py test SOURCE  # fetch one source and print what it returns

No dependencies beyond the Python standard library. State lives in
data/jobs.json; digests land in digests/. Edit sources.json to add or
disable sources, and radar/match.py to tune matching.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radarlib import fetchers, match, state
from radarlib.digest import render_digest, write_digest
from radarlib.html_digest import write_html

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCES_PATH = os.path.join(ROOT, "sources.json")

# Cap per-run detail fetches (Workday descriptions etc.) to stay polite.
MAX_DETAIL_FETCHES_PER_SOURCE = 40


def load_sources() -> dict:
    with open(SOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)["sources"]


def enrich_and_score(job: dict, cfg: dict) -> dict:
    """Parse pay and score one normalized job dict (mutates and returns it)."""
    text = f"{job['title']} {job.get('description', '')}"
    lo, hi, raw = match.parse_pay(text)
    job["pay_min_hr"], job["pay_max_hr"], job["pay_raw"] = lo, hi, raw
    job["desc_hc"] = match.desc_has_healthcare(job.get("description", ""))
    if cfg.get("force_location"):
        # Some boards (Howard Center's UKG) report departments, not towns.
        if job["location"] and job["location"] != cfg["force_location"]:
            job["title"] = f"{job['title']} — {job['location']}"
        job["location"] = cfg["force_location"]
    elif not job["location"] and cfg.get("default_location"):
        job["location"] = cfg["default_location"]
    tier, score, reasons = match.score_job(
        job["title"], job["location"], job["remote"],
        lo, hi, job.get("description", ""),
        location_exempt=bool(cfg.get("location_exempt")),
        desc_healthcare=job["desc_hc"])
    job["tier"], job["score"], job["reasons"] = tier, score, reasons
    return job


def fetch_source(source_key: str, cfg: dict, known_ids: set,
                 needs_pay_ids: set = frozenset()) -> list[dict]:
    fetcher = fetchers.FETCHERS[cfg["ats"]]
    raw_jobs = fetcher(cfg)

    # Some ATSes (Workday, Oracle, State of VT) don't include pay/description
    # in the list view. Fetch full text for new or not-yet-pay-checked relevant
    # jobs, bounded per run, so pay parsing has something to read while
    # staying polite. Daily runs keep topping up until everything's checked.
    detail_fn = fetchers.DETAIL_FETCHERS.get(cfg["ats"])
    if detail_fn:
        budget = MAX_DETAIL_FETCHES_PER_SOURCE
        for job in raw_jobs:
            job_id = f"{source_key}:{job['ats_id']}"
            already_handled = job_id in known_ids and job_id not in needs_pay_ids
            if budget <= 0 or already_handled or job.get("description"):
                continue
            preview_tier, _, _ = match.score_job(
                job["title"], job["location"] or cfg.get("default_location", ""),
                job["remote"], None, None,
                location_exempt=bool(cfg.get("location_exempt")))
            if preview_tier == "skip":
                continue
            try:
                job["description"] = detail_fn(cfg, job)
                budget -= 1
                job["pay_checked"] = True
            except Exception:
                pass  # description stays empty; pay just won't be parsed
    # Drop malformed items (no stable ID or no title) and dedupe by ID so a
    # bad response can't collapse records or churn the state file.
    cleaned: dict[str, dict] = {}
    for job in raw_jobs:
        job.pop("_detail_path", None)
        job.pop("_needs_detail", None)
        if not job.get("ats_id") or not job.get("title"):
            continue
        enrich_and_score(job, cfg)
        cleaned[job["ats_id"]] = job
    return list(cleaned.values())


def cmd_run(open_after: bool = False) -> int:
    sources = load_sources()
    db = state.load()
    known_ids = set(db["jobs"])
    # Interesting jobs we've never pulled pay info for (detail-fetch ATSes).
    needs_pay_ids = {jid for jid, j in db["jobs"].items()
                     if j["status"] == "open" and j["tier"] in ("best", "look")
                     and j.get("pay_raw") is None and not j.get("pay_checked")}
    changes_by_source, fetch_errors = {}, {}

    for key, cfg in sources.items():
        if not cfg.get("enabled", True):
            continue
        label = f"{cfg['employer']} [{cfg['ats']}]"
        print(f"fetching {label} ...", flush=True)
        try:
            jobs = fetch_source(key, cfg, known_ids, needs_pay_ids)
            # A previously healthy source suddenly reporting zero jobs is far
            # more likely a broken response than a mass takedown — treat as a
            # failure so we don't close everything.
            open_before = sum(1 for j in db["jobs"].values()
                              if j["source"] == key and j["status"] == "open")
            if not jobs and open_before > 2:
                raise RuntimeError(
                    f"returned 0 jobs but {open_before} were open — "
                    "refusing to mass-close (likely a broken response)")
            # Don't lose pay or description info parsed on an earlier run just
            # because today's list view doesn't include it: re-score with the
            # remembered signals.
            for job in jobs:
                existing = db["jobs"].get(f"{key}:{job['ats_id']}")
                if not existing:
                    continue
                changed = False
                if job.get("pay_raw") is None and existing.get("pay_raw"):
                    job["pay_min_hr"] = existing["pay_min_hr"]
                    job["pay_max_hr"] = existing["pay_max_hr"]
                    job["pay_raw"] = existing["pay_raw"]
                    changed = True
                if existing.get("desc_hc") and not job.get("desc_hc"):
                    job["desc_hc"] = True
                    changed = True
                if changed:
                    job["tier"], job["score"], job["reasons"] = match.score_job(
                        job["title"], job["location"], job["remote"],
                        job["pay_min_hr"], job["pay_max_hr"],
                        job.get("description", ""),
                        location_exempt=bool(cfg.get("location_exempt")),
                        desc_healthcare=bool(job.get("desc_hc")))
            changes = state.merge_fetched(db, key, cfg["employer"], jobs,
                                          rotating_feed_days=cfg.get("rotating_feed_days"))
            changes_by_source[key] = changes
            print(f"  {len(jobs)} listings | +{len(changes['new'])} new, "
                  f"-{len(changes['closed'])} closed")
        except Exception as err:
            fetch_errors[label] = str(err)[:300]
            print(f"  FAILED: {err}", file=sys.stderr)

    state.save(db)
    digest_md = render_digest(db, changes_by_source, fetch_errors)
    dated, latest = write_digest(digest_md)
    html_path = write_html(db)
    print(f"\ndigest written: {os.path.relpath(dated, ROOT)} "
          f"+ {os.path.relpath(html_path, ROOT)}")

    if open_after:
        subprocess.run(["open", html_path], check=False)
    # Exit nonzero only if EVERY source failed (so Actions flags real outages).
    return 1 if fetch_errors and not changes_by_source else 0


def cmd_sources() -> int:
    sources = load_sources()
    db = state.load()
    for key, cfg in sources.items():
        n_open = sum(1 for j in db["jobs"].values()
                     if j["source"] == key and j["status"] == "open")
        flag = "" if cfg.get("enabled", True) else "  (DISABLED)"
        print(f"{key:24} {cfg['ats']:14} {n_open:4} open   {cfg['employer']}{flag}")
    return 0


def cmd_test(source_key: str) -> int:
    cfg = load_sources()[source_key]
    jobs = fetch_source(source_key, cfg, known_ids=set())
    for j in jobs[:50]:
        pay = j.get("pay_raw") or "no pay info"
        print(f"[{j['tier']:4}] {j['title']}  ({j['location']})  {pay}")
    print(f"\n{len(jobs)} listings from {cfg['employer']}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "run":
        sys.exit(cmd_run(open_after="--open" in args))
    elif args[0] == "render":
        # Re-render digest + web page from the existing database (no fetching).
        db = state.load()
        write_digest(render_digest(db, {}, {}))
        path = write_html(db)
        print(f"re-rendered {os.path.relpath(path, ROOT)}")
        if "--open" in args:
            subprocess.run(["open", path], check=False)
        sys.exit(0)
    elif args[0] == "sources":
        sys.exit(cmd_sources())
    elif args[0] == "test" and len(args) > 1:
        sys.exit(cmd_test(args[1]))
    else:
        print(__doc__)
        sys.exit(2)
