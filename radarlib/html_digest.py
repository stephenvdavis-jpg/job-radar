"""Render the digest as a self-contained web page (docs/index.html).

Published via GitHub Pages so the digest is a bookmarkable, phone-friendly
page — no code or GitHub account needed to read it.
"""

import html
import os
from datetime import date, datetime, timezone

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")


def _e(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def _pay_html(job: dict) -> str:
    if job.get("pay_raw"):
        lo, hi = job.get("pay_min_hr"), job.get("pay_max_hr")
        if lo is not None and hi is not None:
            approx = f"${lo:.0f}/hr" if lo == hi else f"${lo:.0f}–${hi:.0f}/hr"
            return f"{_e(job['pay_raw'])} <span class='approx'>≈{approx}</span>"
        return _e(job["pay_raw"])
    return "<span class='nopay'>pay not listed</span>"


def _card(job: dict, today: str) -> str:
    where = job["location"] or ("Remote" if job["remote"] else "")
    badges = []
    if job["first_seen"] == today:
        badges.append("<span class='badge new'>NEW</span>")
    if job.get("pay_min_hr") is not None and job["pay_min_hr"] >= 25:
        badges.append("<span class='badge pay'>$25+/hr</span>")
    if job["remote"]:
        badges.append("<span class='badge rem'>remote-friendly</span>")
    posted = f" · posted {job['posted_at']}" if job.get("posted_at") else ""
    return f"""<a class="card" href="{_e(job['url'])}" target="_blank" rel="noopener">
  <div class="row"><span class="title">{_e(job['title'])}</span>{''.join(badges)}</div>
  <div class="meta">{_e(job['employer'])} · {_e(where)}</div>
  <div class="meta">{_pay_html(job)}{_e(posted)} · listed since {_e(job['first_seen'])}</div>
</a>"""


def render_html(db: dict) -> str:
    jobs = db["jobs"]
    today = date.today().isoformat()
    open_jobs = [j for j in jobs.values() if j["status"] == "open"]
    new_today = [j for j in open_jobs if j["first_seen"] == today]
    closed_today = [j for j in jobs.values()
                    if j["status"] == "closed" and j.get("closed_on") == today]

    def sortkey(j):
        return (-j["score"], j["employer"], j["title"])

    best = sorted((j for j in open_jobs if j["tier"] == "best"), key=sortkey)
    look = sorted((j for j in open_jobs if j["tier"] == "look"), key=sortkey)
    skip = sorted((j for j in open_jobs if j["tier"] == "skip"), key=sortkey)

    best_html = "\n".join(_card(j, today) for j in best) or "<p class='empty'>none right now</p>"
    look_html = "\n".join(_card(j, today) for j in look) or "<p class='empty'>none right now</p>"
    skip_html = "\n".join(
        f"<li><a href='{_e(j['url'])}' target='_blank' rel='noopener'>{_e(j['title'])}</a>"
        f" — {_e(j['employer'])}"
        f"{(' · <em>' + _e(j['reasons'][0]) + '</em>') if j.get('reasons') else ''}</li>"
        for j in skip)
    closed_html = "\n".join(
        f"<li>{_e(j['title'])} — {_e(j['employer'])}</li>" for j in closed_today)

    updated = datetime.now(timezone.utc).strftime("%B %-d, %Y at %H:%M UTC")
    n_new_interesting = sum(1 for j in new_today if j["tier"] in ("best", "look"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Burlington Job Radar</title>
<style>
  :root {{
    --bg: #faf9f7; --card: #ffffff; --ink: #1a1a1a; --muted: #6b6b6b;
    --line: #e5e2dd; --accent: #1f6f4a; --gold: #b07d18; --link: #14532d;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16181a; --card: #1f2225; --ink: #ececec; --muted: #9aa0a6;
      --line: #33373b; --accent: #4cc38a; --gold: #e2b04a; --link: #7fd6a9;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink);
         font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 20px 16px 60px; }}
  header h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
  header p {{ margin: 0 0 4px; color: var(--muted); }}
  .stats {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 14px 0 6px; }}
  .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px;
           padding: 8px 14px; text-align: center; }}
  .stat b {{ display: block; font-size: 1.25rem; }}
  .stat span {{ font-size: .78rem; color: var(--muted); }}
  #filter {{ width: 100%; margin: 14px 0 4px; padding: 10px 14px; font-size: 1rem;
             border: 1px solid var(--line); border-radius: 10px;
             background: var(--card); color: var(--ink); }}
  h2 {{ font-size: 1.15rem; margin: 26px 0 10px; }}
  .card {{ display: block; background: var(--card); border: 1px solid var(--line);
           border-radius: 12px; padding: 12px 14px; margin: 8px 0;
           text-decoration: none; color: var(--ink); }}
  .card:hover {{ border-color: var(--accent); }}
  .row {{ display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }}
  .title {{ font-weight: 600; color: var(--link); }}
  .meta {{ font-size: .86rem; color: var(--muted); margin-top: 2px; }}
  .approx {{ color: var(--accent); font-weight: 600; }}
  .nopay {{ font-style: italic; }}
  .badge {{ font-size: .68rem; font-weight: 700; padding: 2px 7px; border-radius: 20px;
            letter-spacing: .03em; white-space: nowrap; }}
  .badge.new {{ background: var(--accent); color: #fff; }}
  .badge.pay {{ background: color-mix(in srgb, var(--gold) 18%, transparent); color: var(--gold); }}
  .badge.rem {{ background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }}
  details {{ margin-top: 26px; }}
  summary {{ cursor: pointer; font-weight: 600; }}
  details ul {{ padding-left: 20px; color: var(--muted); font-size: .88rem; }}
  details a {{ color: inherit; }}
  .empty {{ color: var(--muted); font-style: italic; }}
  footer {{ margin-top: 40px; font-size: .8rem; color: var(--muted); }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Burlington Job Radar</h1>
  <p>Jobs within ~30 min of Burlington VT (or remote), $25/hr and up, updated every morning.</p>
  <p>Last updated {updated}</p>
</header>

<div class="stats">
  <div class="stat"><b>{len(best)}</b><span>best matches</span></div>
  <div class="stat"><b>{len(look)}</b><span>worth a look</span></div>
  <div class="stat"><b>{len(new_today)}</b><span>new today ({n_new_interesting} interesting)</span></div>
  <div class="stat"><b>{len(open_jobs)}</b><span>tracked</span></div>
</div>

<input id="filter" type="search" placeholder="Filter by job title or employer…"
       oninput="f(this.value)">

<h2>⭐ Best matches</h2>
{best_html}

<h2>👀 Worth a look</h2>
{look_html}

{f"<details><summary>❌ Closed today ({len(closed_today)})</summary><ul>{closed_html}</ul></details>" if closed_today else ""}

<details><summary>🗑 Probably skip ({len(skip)} listings that didn't fit — with reasons)</summary>
<ul>
{skip_html}
</ul>
</details>

<footer>Sources: UVM Medical Center, Howard Center, State of Vermont, UVM,
Community Health Centers of Burlington, BlueCross VT, the cities and colleges,
Seven Days Jobs, Common Good VT, and a dozen more — all read from their public
job feeds. Pay shown only when the posting lists it.</footer>
</div>
<script>
function f(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.card').forEach(function (c) {{
    c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>
"""


def write_html(db: dict) -> str:
    os.makedirs(DOCS_DIR, exist_ok=True)
    path = os.path.join(DOCS_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(db))
    return path
