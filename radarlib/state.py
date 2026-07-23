"""Load/save the job database (a single JSON file, friendly to git diffs)."""

import json
import os
from datetime import date

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.json")


def today() -> str:
    return date.today().isoformat()


def load() -> dict:
    if not os.path.exists(DATA_PATH):
        return {"jobs": {}, "meta": {}}
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(db: dict) -> None:
    db["meta"]["last_run"] = today()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def merge_fetched(db: dict, source_key: str, employer: str, fetched: list[dict],
                  rotating_feed_days: int | None = None) -> dict:
    """Merge one source's fetch into the DB. Returns a change summary.

    rotating_feed_days: for feeds that only show the N newest postings
    (Seven Days RSS), absence doesn't mean closed — instead, close a job
    only after it hasn't been seen for this many days.
    """
    changes = {"new": [], "reopened": [], "closed": [], "updated": []}
    seen_ids = set()
    run_date = today()

    for j in fetched:
        job_id = f"{source_key}:{j['ats_id']}"
        seen_ids.add(job_id)
        fingerprint = f"{j['title']}|{j['location']}|{j.get('pay_raw') or ''}"
        existing = db["jobs"].get(job_id)
        if existing is None:
            record = {
                "source": source_key, "employer": employer,
                "title": j["title"], "location": j["location"], "url": j["url"],
                "remote": j["remote"], "posted_at": j.get("posted_at"),
                "pay_min_hr": j.get("pay_min_hr"), "pay_max_hr": j.get("pay_max_hr"),
                "pay_raw": j.get("pay_raw"),
                "tier": j["tier"], "score": j["score"], "reasons": j["reasons"],
                "status": "open", "first_seen": run_date, "last_seen": run_date,
                "fingerprint": fingerprint,
                "pay_checked": bool(j.get("pay_checked")),
                "desc_hc": bool(j.get("desc_hc")),
            }
            db["jobs"][job_id] = record
            changes["new"].append(job_id)
        else:
            if existing["status"] == "closed":
                existing["status"] = "open"
                existing.pop("closed_on", None)
                changes["reopened"].append(job_id)
            elif existing.get("fingerprint") != fingerprint:
                changes["updated"].append(job_id)
            existing.update({
                "title": j["title"], "location": j["location"], "url": j["url"],
                "remote": j["remote"],
                "pay_min_hr": j.get("pay_min_hr") or existing.get("pay_min_hr"),
                "pay_max_hr": j.get("pay_max_hr") or existing.get("pay_max_hr"),
                "pay_raw": j.get("pay_raw") or existing.get("pay_raw"),
                "tier": j["tier"], "score": j["score"], "reasons": j["reasons"],
                "last_seen": run_date, "fingerprint": fingerprint,
                "pay_checked": existing.get("pay_checked") or bool(j.get("pay_checked")),
                "desc_hc": existing.get("desc_hc") or bool(j.get("desc_hc")),
            })
            if j.get("posted_at"):
                existing["posted_at"] = j["posted_at"]

    # Anything from this source not seen in this fetch has been taken down
    # (or, for rotating feeds, merely rolled off — use an age threshold).
    for job_id, record in db["jobs"].items():
        if (record["source"] != source_key or record["status"] != "open"
                or job_id in seen_ids):
            continue
        if rotating_feed_days is not None:
            unseen_days = (date.fromisoformat(run_date)
                           - date.fromisoformat(record["last_seen"])).days
            if unseen_days < rotating_feed_days:
                continue
        record["status"] = "closed"
        record["closed_on"] = run_date
        changes["closed"].append(job_id)
    return changes
