"""Per-ATS fetchers. Each returns a list of normalized job dicts:

    {"ats_id": str, "title": str, "location": str, "url": str,
     "remote": bool, "posted_at": str|None, "description": str}

`description` may be empty in list views; the pipeline fetches details only
for new jobs to keep requests polite. Source config lives in sources.json.
"""

import html
import json
import re
from html.parser import HTMLParser

from .http import fetch_json, fetch_text

REMOTE_RE = re.compile(r"\b(remote|telework|work from home|virtual)\b", re.I)


def _is_remote(*fields: str) -> bool:
    return any(REMOTE_RE.search(f or "") for f in fields)


class _TextExtractor(HTMLParser):
    """Strip tags from an HTML fragment, keeping readable text."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def html_to_text(fragment: str) -> str:
    parser = _TextExtractor()
    parser.feed(html.unescape(fragment or ""))
    return parser.text()


# --- Greenhouse -------------------------------------------------------------

def fetch_greenhouse(cfg: dict) -> list[dict]:
    token = cfg["board_token"]
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        desc = html_to_text(j.get("content", ""))
        jobs.append({
            "ats_id": str(j["id"]),
            "title": j.get("title", ""),
            "location": loc,
            "url": j.get("absolute_url", ""),
            "remote": _is_remote(loc, j.get("title", "")),
            "posted_at": (j.get("first_published") or j.get("updated_at") or "")[:10] or None,
            "description": desc,
        })
    return jobs


# --- Lever ------------------------------------------------------------------

def fetch_lever(cfg: dict) -> list[dict]:
    company = cfg["company"]
    data = fetch_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
    jobs = []
    for j in data:
        loc = (j.get("categories") or {}).get("location", "") or ""
        jobs.append({
            "ats_id": j["id"],
            "title": j.get("text", ""),
            "location": loc,
            "url": j.get("hostedUrl", ""),
            "remote": _is_remote(loc, j.get("workplaceType", "")),
            "posted_at": None,
            "description": html_to_text(j.get("descriptionPlain") or j.get("description") or ""),
        })
    return jobs


# --- SmartRecruiters --------------------------------------------------------

def fetch_smartrecruiters(cfg: dict) -> list[dict]:
    company = cfg["company"]
    jobs, offset = [], 0
    while True:
        data = fetch_json(
            f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset={offset}")
        content = data.get("content", [])
        for j in content:
            loc_parts = [j.get("location", {}).get(k, "") for k in ("city", "region")]
            loc = ", ".join(p for p in loc_parts if p)
            jobs.append({
                "ats_id": str(j["id"]),
                "title": j.get("name", ""),
                "location": loc,
                "url": f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
                "remote": bool(j.get("location", {}).get("remote")) or _is_remote(loc),
                "posted_at": (j.get("releasedDate") or "")[:10] or None,
                "description": "",
            })
        offset += len(content)
        if len(content) < 100 or offset >= data.get("totalFound", 0):
            break
    return jobs


# --- Workday (CxS public API) ----------------------------------------------

def _workday_base(cfg: dict) -> str:
    return f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}"

def fetch_workday(cfg: dict) -> list[dict]:
    base = _workday_base(cfg)
    jobs, offset = [], 0
    search_text = cfg.get("search_text", "")
    applied_facets = cfg.get("facets", {})
    while True:
        data = fetch_json(f"{base}/jobs", post_json={
            "limit": 20, "offset": offset,
            "searchText": search_text, "appliedFacets": applied_facets,
        })
        postings = data.get("jobPostings", [])
        for j in postings:
            path = j.get("externalPath", "")
            loc = j.get("locationsText", "")
            # Prefer the stable requisition token ("...Care-Coordinator_R0087213"
            # -> "R0087213") so a title edit doesn't look like closed+new.
            slug = path.rsplit("/", 1)[-1]
            req = re.search(r"_([A-Za-z0-9-]+)$", slug)
            jobs.append({
                "ats_id": (req.group(1) if req else slug) or path,
                "title": j.get("title", ""),
                "location": loc,
                "url": f"https://{cfg['host']}/{cfg['site']}{path.replace('/job/', '/job/', 1)}"
                       if not path.startswith("http") else path,
                "remote": _is_remote(loc, j.get("title", "")),
                "posted_at": None,  # list view only says "Posted 3 Days Ago"
                "description": "",
                "_detail_path": path,
            })
        offset += len(postings)
        # "total" is only reliable on the first page; stop on a short page.
        if len(postings) < 20 or offset >= 2000:
            break
    return jobs

def fetch_workday_detail(cfg: dict, detail_path: str) -> str:
    """Fetch one job's full description text (used for pay parsing)."""
    data = fetch_json(f"{_workday_base(cfg)}{detail_path}")
    info = data.get("jobPostingInfo", {})
    return html_to_text(info.get("jobDescription", ""))


# --- UKG Pro Recruiting -----------------------------------------------------

def fetch_ukgpro(cfg: dict) -> list[dict]:
    # cfg["base_url"] like https://HOST/TENANT/JobBoard/BOARD-GUID (no trailing /)
    base = cfg["base_url"].rstrip("/")
    jobs, skip = [], 0
    while True:
        data = fetch_json(
            f"{base}/JobBoardView/LoadSearchResults",
            post_json={"opportunitySearch": {
                "Top": 50, "Skip": skip, "QueryString": "",
                "OrderBy": [{"Value": "postedDateUtc", "PropertyName": "PostedDate",
                             "Ascending": False}],
                "Filters": []}, "matchCriteria": {"PreferredJobs": [], "Educations": [],
                "LicenseAndCertifications": [], "Skills": [], "hasNoLicenses": False,
                "SkippedSkills": []}},
            headers={"Accept": "application/json"})
        opps = data.get("opportunities", [])
        for j in opps:
            loc_names = []
            for l in (j.get("Locations") or []):
                if not isinstance(l, dict):
                    continue
                name = l.get("LocalizedName")
                if not name:
                    addr = l.get("Address")
                    if isinstance(addr, dict):
                        city = addr.get("City")
                        name = city.get("Name") if isinstance(city, dict) else city
                if name:
                    loc_names.append(str(name))
            loc = "; ".join(loc_names)
            jobs.append({
                "ats_id": j.get("Id", ""),
                "title": j.get("Title", ""),
                "location": loc,
                "url": f"{base}/OpportunityDetail?opportunityId={j.get('Id', '')}",
                "remote": _is_remote(loc, j.get("Title", "")),
                "posted_at": (j.get("PostedDate") or "")[:10] or None,
                "description": html_to_text(j.get("BriefDescription") or ""),
            })
        skip += len(opps)
        if len(opps) < 50 or skip >= data.get("totalCount", 0):
            break
    return jobs


# --- Paylocity --------------------------------------------------------------

def fetch_paylocity(cfg: dict) -> list[dict]:
    data = fetch_json(
        f"https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{cfg['company_id']}")
    jobs = []
    for j in data.get("jobs", []):
        loc = ", ".join(filter(None, [
            (j.get("location") or {}).get("city", ""),
            (j.get("location") or {}).get("state", "")]))
        jobs.append({
            "ats_id": str(j.get("jobId") or j.get("id", "")),
            "title": j.get("title", ""),
            "location": loc,
            "url": j.get("applyUrl") or j.get("detailUrl", ""),
            "remote": _is_remote(loc, j.get("title", "")),
            "posted_at": (j.get("publishedDate") or "")[:10] or None,
            "description": html_to_text(j.get("description", "")),
        })
    return jobs


# --- ADP Workforce Now ------------------------------------------------------

def fetch_adp(cfg: dict) -> list[dict]:
    cid = cfg["cid"]
    cc_id = cfg.get("cc_id", "19000101_000001")
    base = ("https://workforcenow.adp.com/mascsr/default/careercenter/public/"
            f"events/staffing/v1/job-requisitions?cid={cid}&ccId={cc_id}&lang=en_US")
    jobs, skip = [], 0
    while True:
        data = fetch_json(f"{base}&%24top=50&%24skip={skip}")
        reqs = data.get("jobRequisitions", [])
        for j in reqs:
            req_id = str(j.get("itemID") or (j.get("customFieldGroup") or {}).get("itemID", ""))
            locs = j.get("requisitionLocations") or []
            loc = ", ".join(filter(None, [
                (locs[0].get("address") or {}).get("cityName", "") if locs else "",
                ((locs[0].get("address") or {}).get("countrySubdivisionLevel1") or {}).get("codeValue", "")
                if locs else ""]))
            title = (j.get("requisitionTitle") or "")
            apply_url = (f"https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
                         f"recruitment.html?cid={cid}&ccId={cc_id}&lang=en_US&jobId={req_id}")
            posted = ((j.get("postDate") or "")[:10]) or None
            jobs.append({
                "ats_id": req_id,
                "title": title,
                "location": loc,
                "url": apply_url,
                "remote": _is_remote(loc, title),
                "posted_at": posted,
                "description": html_to_text(j.get("requisitionDescription", "")),
            })
        skip += len(reqs)
        if len(reqs) < 50:
            break
    return jobs


# --- Atom/RSS feeds (e.g. UVM's PeopleAdmin at uvmjobs.com) ----------------

def fetch_atom(cfg: dict) -> list[dict]:
    import xml.etree.ElementTree as ET
    raw = fetch_text(cfg["url"])
    root = ET.fromstring(raw)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns) or root.findall(".//item")
    jobs = []
    for e in entries:
        if e.tag.endswith("entry"):  # Atom
            title = (e.findtext("a:title", "", ns) or "").strip()
            link_el = e.find("a:link", ns)
            url = link_el.get("href", "") if link_el is not None else ""
            uid = e.findtext("a:id", "", ns) or url
            summary = e.findtext("a:summary", "", ns) or e.findtext("a:content", "", ns) or ""
            posted = (e.findtext("a:published", "", ns) or e.findtext("a:updated", "", ns))[:10] or None
        else:  # RSS
            title = (e.findtext("title") or "").strip()
            url = (e.findtext("link") or "").strip()
            uid = e.findtext("guid") or url
            summary = e.findtext("description") or ""
            posted = None
        # WP Job Manager feeds (Seven Days Jobs) carry namespaced
        # <job_listing:location>/<job_listing:company> children.
        loc = company = ""
        for child in e:
            tag = child.tag.lower()
            if tag.endswith("location") and child.text:
                loc = child.text.strip()
            elif tag.endswith("company") and child.text:
                company = child.text.strip()
        if company:
            title = f"{title} ({company})"
        loc = loc or cfg.get("default_location", "")
        jobs.append({
            "ats_id": uid.rsplit("/", 1)[-1] or uid,
            "title": title,
            "location": loc,
            "url": url,
            "remote": _is_remote(title, summary),
            "posted_at": posted,
            "description": html_to_text(summary),
        })
    return jobs


# --- Oracle Cloud Recruiting (Champlain College, Saint Michael's) ----------

def fetch_oracle_orc(cfg: dict) -> list[dict]:
    tenant, site = cfg["tenant"], cfg["site"]  # e.g. champlain-ibumjb, CX_1
    base = f"https://{tenant}.fa.ocs.oraclecloud.com"
    url = (f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
           f"?onlyData=true&expand=requisitionList.secondaryLocations"
           f"&finder=findReqs;siteNumber={site},limit=100,"
           f"sortBy=POSTING_DATES_DESC")
    data = fetch_json(url)
    items = (data.get("items") or [{}])[0].get("requisitionList", [])
    jobs = []
    for j in items:
        rid = str(j.get("Id", ""))
        loc = j.get("PrimaryLocation", "") or ""
        jobs.append({
            "ats_id": rid,
            "title": j.get("Title", ""),
            "location": loc,
            "url": (f"{base}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}"),
            "remote": _is_remote(loc, j.get("Title", "")),
            "posted_at": (j.get("PostedDate") or "")[:10] or None,
            "description": html_to_text(j.get("ShortDescriptionStr", "")),
        })
    return jobs

def fetch_oracle_orc_detail(cfg: dict, job: dict) -> str:
    tenant, site = cfg["tenant"], cfg["site"]
    url = (f"https://{tenant}.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/"
           f"recruitingCEJobRequisitionDetails?onlyData=true&expand=all"
           f"&finder=ById;siteNumber={site},Id=%22{job['ats_id']}%22")
    data = fetch_json(url)
    items = data.get("items", [])
    if not items:
        return ""
    return html_to_text(items[0].get("ExternalDescriptionStr", "") or "")


# --- Workable (OnLogic) -----------------------------------------------------

def fetch_workable(cfg: dict) -> list[dict]:
    account = cfg["account"]
    data = fetch_json(
        f"https://apply.workable.com/api/v1/widget/accounts/{account}?details=true")
    jobs = []
    for j in data.get("jobs", []):
        loc = ", ".join(filter(None, [j.get("city", ""), j.get("state", "")]))
        jobs.append({
            "ats_id": str(j.get("shortcode") or j.get("id", "")),
            "title": j.get("title", ""),
            "location": loc,
            "url": j.get("url") or j.get("application_url", ""),
            "remote": bool(j.get("telecommuting")) or _is_remote(loc, j.get("title", "")),
            "posted_at": (j.get("published_on") or "")[:10] or None,
            "description": html_to_text(j.get("description", "")),
        })
    return jobs


# --- BambooHR ---------------------------------------------------------------

def fetch_bamboohr(cfg: dict) -> list[dict]:
    sub = cfg["subdomain"]
    data = fetch_json(f"https://{sub}.bamboohr.com/careers/list",
                      headers={"Accept": "application/json"})
    jobs = []
    for j in data.get("result", []):
        loc_d = j.get("location") or {}
        loc = ", ".join(filter(None, [loc_d.get("city", ""), loc_d.get("state", "")]))
        jobs.append({
            "ats_id": str(j.get("id", "")),
            "title": j.get("jobOpeningName", ""),
            "location": loc,
            "url": f"https://{sub}.bamboohr.com/careers/{j.get('id', '')}",
            "remote": bool(j.get("isRemote")) or _is_remote(loc),
            "posted_at": None,
            "description": "",
        })
    return jobs


# --- NeoGov / governmentjobs.com (City of Burlington etc.) ------------------

_NEOGOV_ITEM = re.compile(
    r'<a[^>]+class="[^"]*item-details-link[^"]*"[^>]+href="(?P<url>[^"]+)"[^>]*>'
    r'\s*(?P<title>[^<]+)</a>(?P<rest>.*?)(?=<a[^>]+item-details-link|$)', re.S)
_NEOGOV_SALARY = re.compile(
    r'<td[^>]*class="[^"]*job-table-salary[^"]*"[^>]*>(?P<sal>[^<]*)')

def fetch_neogov(cfg: dict) -> list[dict]:
    slug = cfg["agency"]
    jobs = []
    for page in range(1, cfg.get("max_pages", 3) + 1):
        # The XHR header makes NeoGov return a server-rendered partial
        # instead of the JS app shell.
        page_html = fetch_text(
            f"https://www.governmentjobs.com/careers/{slug}?page={page}",
            headers={"Accept": "text/html",
                     "X-Requested-With": "XMLHttpRequest"})
        found = list(_NEOGOV_ITEM.finditer(page_html))
        for m in found:
            url = html.unescape(m.group("url"))
            if url.startswith("/"):
                url = "https://www.governmentjobs.com" + url
            rest = m.group("rest")
            sal_m = _NEOGOV_SALARY.search(rest)
            salary_text = html_to_text(sal_m.group("sal")) if sal_m else ""
            title = html_to_text(m.group("title"))
            # URL shape: /careers/{agency}/jobs/{numeric-id}/{title-slug} —
            # key on the numeric ID; the title slug changes when titles do.
            num = re.search(r"/jobs/(\d+)", url)
            jobs.append({
                "ats_id": num.group(1) if num
                          else url.rstrip("/").rsplit("/", 1)[-1].split("?")[0],
                "title": title,
                "location": cfg.get("default_location", ""),
                "url": url,
                "remote": _is_remote(title),
                "posted_at": None,
                "description": salary_text,  # salary line feeds the pay parser
            })
        if not found:
            break
    # Each posting appears twice (card + table view); keep the one with salary.
    by_id: dict[str, dict] = {}
    for j in jobs:
        prev = by_id.get(j["ats_id"])
        if prev is None or (j["description"] and not prev["description"]):
            by_id[j["ats_id"]] = j
    return list(by_id.values())


# --- State of Vermont (SuccessFactors; via sitemap diffing) -----------------

_VT_JOB_URL = re.compile(r"careers\.vermont\.gov/job/([^/]+)/(\d+)/?")

def fetch_vt_state(cfg: dict) -> list[dict]:
    sitemap = fetch_text("https://careers.vermont.gov/sitemap.xml")
    jobs, seen = [], set()
    for m in _VT_JOB_URL.finditer(sitemap):
        slug, job_id = html.unescape(m.group(1)), m.group(2)
        if job_id in seen:
            continue
        seen.add(job_id)
        # Slug looks like "Burlington-Program-Technician-I-VT-05401"; the
        # leading token(s) are the town, the rest the title.
        words = slug.replace("%2D", "-").split("-")
        loc_words, title_words = [], list(words)
        # Two-word towns only when the pair actually is one ("South Burlington",
        # "Essex Junction", "Saint Albans") — not "Essex Residential ...".
        two_word_towns = {("south", "burlington"), ("south", "hero"),
                          ("essex", "junction"), ("saint", "albans"),
                          ("st", "albans"), ("saint", "johnsbury"),
                          ("st", "johnsbury"), ("white", "river"),
                          ("st", "george"), ("saint", "george")}
        if len(words) > 1 and (words[0].lower(), words[1].lower()) in two_word_towns:
            loc_words, title_words = words[:2], words[2:]
        elif words:
            loc_words, title_words = words[:1], words[1:]
        title = " ".join(w for w in title_words if not w.isdigit() and w.upper() != "VT")
        location = " ".join(loc_words) + ", VT"
        jobs.append({
            "ats_id": job_id,
            "title": title,
            "location": location,
            "url": f"https://careers.vermont.gov/job/{slug}/{job_id}/",
            "remote": _is_remote(title),
            "posted_at": None,
            "description": "",
            "_needs_detail": True,
        })
    return jobs

def fetch_vt_state_detail(cfg: dict, job: dict) -> str:
    # Pay lives in a custom-field span outside the description block, so feed
    # the whole page's text to the pay parser rather than just the description.
    page = fetch_text(job["url"], headers={"Accept": "text/html"})
    return html_to_text(page)


# --- WP Job Manager via WordPress REST API (Common Good Vermont) ------------

def fetch_wp_jobs(cfg: dict) -> list[dict]:
    site = cfg["site"].rstrip("/")
    regions: dict[int, str] = {}
    try:
        for t in fetch_json(f"{site}/wp-json/wp/v2/job_listing_region?per_page=100"):
            regions[t["id"]] = t.get("name", "")
    except Exception:
        pass  # regions stay unnamed; default_location applies
    jobs, page = [], 1
    while page <= 4:
        try:
            data = fetch_json(f"{site}/wp-json/wp/v2/job-listings?per_page=50&page={page}")
        except RuntimeError:
            if page == 1:
                raise  # a failing board must fail loudly, not close every job
            break  # WP returns 400 past the last page
        if not data:
            break
        for j in data:
            meta = j.get("meta") or {}
            company = meta.get("_company_name", "")
            title = html_to_text(j.get("title", {}).get("rendered", ""))
            if company:
                title = f"{title} ({company})"
            region_ids = j.get("job_listing_region") or []
            loc = ", ".join(filter(None, (regions.get(r, "") for r in region_ids)))
            if loc and "vt" not in loc.lower() and "vermont" not in loc.lower():
                loc += ", VT"
            salary = meta.get("_job_salary", "")
            unit = (meta.get("_job_salary_unit") or "").lower()
            desc = html_to_text(j.get("content", {}).get("rendered", ""))
            if salary:
                unit_word = {"hour": "per hour", "year": "per year"}.get(unit, unit)
                desc = f"Salary: {salary} {unit_word}. {desc}"
            jobs.append({
                "ats_id": str(j["id"]),
                "title": title,
                "location": loc,
                "url": j.get("link", ""),
                "remote": _is_remote(loc, title, desc[:300]),
                "posted_at": (j.get("date") or "")[:10] or None,
                "description": desc,
            })
        if len(data) < 50:
            break
        page += 1
    return jobs


# --- Generic JSON (for one-off endpoints; mapping configured per source) ----

def fetch_generic_json(cfg: dict) -> list[dict]:
    """Config supplies: url, items_path (dot path), and field names."""
    data = fetch_json(cfg["url"])
    items = data
    for key in cfg.get("items_path", "").split("."):
        if key:
            items = items[key]
    f = cfg["fields"]  # {"ats_id": "id", "title": "title", ...}
    jobs = []
    for j in items:
        loc = str(j.get(f.get("location", ""), ""))
        jobs.append({
            "ats_id": str(j.get(f["ats_id"], "")),
            "title": str(j.get(f["title"], "")),
            "location": loc,
            "url": cfg.get("url_prefix", "") + str(j.get(f.get("url", ""), "")),
            "remote": _is_remote(loc),
            "posted_at": None,
            "description": "",
        })
    return jobs


# --- Generic HTML via regex (last-resort fallback, no login, read-only) -----

def fetch_generic_html(cfg: dict) -> list[dict]:
    """Config supplies: url, item_regex with named groups (ats_id/title/url,
    optional location). Fragile by design — only for simple public pages."""
    page = fetch_text(cfg["url"])
    jobs = []
    for m in re.finditer(cfg["item_regex"], page, re.S):
        d = m.groupdict()
        url = html.unescape(d.get("url", ""))
        if url and not url.startswith("http"):
            url = cfg.get("url_prefix", "") + url
        title = html_to_text(d.get("title", ""))
        loc = html_to_text(d.get("location", "") or cfg.get("default_location", ""))
        jobs.append({
            "ats_id": d.get("ats_id") or url,
            "title": title,
            "location": loc,
            "url": url,
            "remote": _is_remote(loc, title),
            "posted_at": None,
            "description": "",
        })
    # Boards often render each job link twice (nav + list); dedupe.
    return list({j["ats_id"]: j for j in jobs}.values())


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "smartrecruiters": fetch_smartrecruiters,
    "workday": fetch_workday,
    "ukgpro": fetch_ukgpro,
    "paylocity": fetch_paylocity,
    "adp": fetch_adp,
    "atom": fetch_atom,
    "workable": fetch_workable,
    "wp_jobs": fetch_wp_jobs,
    "oracle_orc": fetch_oracle_orc,
    "bamboohr": fetch_bamboohr,
    "neogov": fetch_neogov,
    "vt_state": fetch_vt_state,
    "generic_json": fetch_generic_json,
    "generic_html": fetch_generic_html,
}

# Optional per-ATS "fetch one job's full text" functions, used only for new,
# plausibly-relevant jobs so pay parsing has something to read.
def _workday_detail(cfg: dict, job: dict) -> str:
    return fetch_workday_detail(cfg, job.get("_detail_path", ""))

DETAIL_FETCHERS = {
    "workday": _workday_detail,
    "oracle_orc": fetch_oracle_orc_detail,
    "vt_state": fetch_vt_state_detail,
}
