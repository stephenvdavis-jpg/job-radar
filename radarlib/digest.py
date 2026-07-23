"""Render the daily digest (markdown for the repo, HTML for local viewing)."""

import os
from datetime import date

DIGEST_DIR = os.path.join(os.path.dirname(__file__), "..", "digests")


def _pay_str(job: dict) -> str:
    if job.get("pay_raw"):
        lo, hi = job.get("pay_min_hr"), job.get("pay_max_hr")
        if lo is not None and hi is not None:
            approx = f"${lo:.0f}/hr" if lo == hi else f"${lo:.0f}–${hi:.0f}/hr"
            return f"{job['pay_raw']} (≈{approx})"
        return job["pay_raw"]
    return "pay not listed"


def _md_label(text: str) -> str:
    """Make arbitrary text safe inside a [label](url) link."""
    return " ".join((text or "").split()).replace("[", "(").replace("]", ")")


def _md_url(url: str) -> str:
    return "<" + (url or "").replace(">", "%3E") + ">" if ")" in (url or "") else url


def _line(job: dict) -> str:
    where = job["location"] or ("Remote" if job["remote"] else "?")
    if job["remote"] and "remote" not in where.lower():
        where += " (remote-friendly)"
    posted = f" · posted {job['posted_at']}" if job.get("posted_at") else ""
    return (f"- **[{_md_label(job['title'])}]({_md_url(job['url'])})** — "
            f"{job['employer']} · {where} · "
            f"{_pay_str(job)}{posted} · first seen {job['first_seen']}")


def _skip_line(job: dict) -> str:
    reason = job["reasons"][0] if job.get("reasons") else ""
    return (f"- [{_md_label(job['title'])}]({_md_url(job['url'])}) — {job['employer']}"
            f"{f' · _{reason}_' if reason else ''}")


def render_digest(db: dict, changes_by_source: dict, fetch_errors: dict) -> str:
    jobs = db["jobs"]
    open_jobs = {jid: j for jid, j in jobs.items() if j["status"] == "open"}
    # Reopened listings deserve the same attention as brand-new ones.
    new_ids = {jid for ch in changes_by_source.values()
               for jid in ch["new"] + ch["reopened"]}
    closed_ids = [jid for ch in changes_by_source.values() for jid in ch["closed"]]

    def sort_key(item):
        return (-item[1]["score"], item[1]["employer"], item[1]["title"])

    best = sorted(((jid, j) for jid, j in open_jobs.items() if j["tier"] == "best"), key=sort_key)
    look = sorted(((jid, j) for jid, j in open_jobs.items() if j["tier"] == "look"), key=sort_key)
    skip = sorted(((jid, j) for jid, j in open_jobs.items() if j["tier"] == "skip"), key=sort_key)

    lines = [f"# Job radar digest — {date.today().isoformat()}", ""]
    n_new_interesting = sum(1 for jid in new_ids if jobs[jid]["tier"] in ("best", "look"))
    lines.append(f"_{len(open_jobs)} open listings tracked · "
                 f"{len(new_ids)} new today ({n_new_interesting} interesting) · "
                 f"{len(closed_ids)} closed today_")
    lines.append("")

    new_interesting = sorted(((jid, jobs[jid]) for jid in new_ids
                              if jobs[jid]["tier"] in ("best", "look")), key=sort_key)
    if new_interesting:
        lines.append("## 🆕 New since last run")
        lines += [_line(j) for _, j in new_interesting]
        lines.append("")

    lines.append(f"## ⭐ Best matches ({len(best)})")
    lines += [_line(j) for _, j in best] or ["- none right now"]
    lines.append("")

    lines.append(f"## 👀 Still open, worth a look ({len(look)})")
    lines += [_line(j) for _, j in look] or ["- none right now"]
    lines.append("")

    if closed_ids:
        lines.append("## ❌ Closed since last run")
        lines += [f"- {jobs[jid]['title']} — {jobs[jid]['employer']}" for jid in closed_ids]
        lines.append("")

    lines.append("<details><summary>🗑 Probably skip "
                 f"({len(skip)} open listings that didn't fit)</summary>")
    lines.append("")
    lines += [_skip_line(j) for _, j in skip[:200]]
    if len(skip) > 200:
        lines.append(f"- …and {len(skip) - 200} more")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    if fetch_errors:
        lines.append("## ⚠️ Sources that failed this run")
        lines += [f"- **{src}**: {' '.join(str(err).split())}"
                  for src, err in fetch_errors.items()]
        lines.append("")
    return "\n".join(lines)


def write_digest(markdown: str) -> tuple[str, str]:
    os.makedirs(DIGEST_DIR, exist_ok=True)
    dated = os.path.join(DIGEST_DIR, f"{date.today().isoformat()}.md")
    latest = os.path.join(DIGEST_DIR, "latest.md")
    for path in (dated, latest):
        with open(path, "w", encoding="utf-8") as f:
            f.write(markdown)
    return dated, latest
