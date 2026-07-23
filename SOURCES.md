# Sources map — Burlington VT job radar

Verified 2026-07-23. "ATS" is the applicant-tracking system behind each careers
page; sources with a public API/feed are automated in `sources.json`. The
radar always reads public pages — no logins, no credentials.

## Automated sources

### Healthcare (Melany's sweet spot)

| Employer | ATS | How we read it | Why it matters |
|---|---|---|---|
| UVM Medical Center | Workday (`uvmhealth` tenant, `EXTERNAL` board) | Public JSON API | The region's flagship hospital, ~130 openings; best MHA pipeline (patient access, practice/program coordinators, quality, revenue cycle) |
| UVM HN Home Health & Hospice (ex-VNA) | Workday (same tenant, `HHH` board) | Public JSON API | Occasional scheduler/coordinator roles in Colchester |
| Community Health Centers of Burlington | ADP Workforce Now | Public JSON API | FQHC with 8 sites; patient services, care coordination, quality |
| Howard Center | UKG Pro Recruiting | Public JSON API (POST) | Largest community mental-health agency in VT — directly thesis-adjacent; ~69 openings |
| Blue Cross Blue Shield of VT | ADP Workforce Now | Public JSON API | Berlin VT but hybrid-friendly (location filter waived); payer-side roles: population health, quality, provider relations |
| MVP Health Care | Workday | Public JSON API | VT/NY insurer; low VT volume, remote roles surface |
| Planned Parenthood of Northern New England | Lever | Public JSON API | Colchester admin office; health-center manager / admin roles |
| Lund | JazzHR | HTML board scrape | Burlington family-services nonprofit |

### Government & education

| Employer | ATS | How we read it | Why it matters |
|---|---|---|---|
| State of Vermont | SAP SuccessFactors | Sitemap diff + detail pages (pay is on detail pages) | ~200 openings; AHS/Health Dept program & admin roles reliably clear $25/hr; Burlington & Waterbury postings common |
| University of Vermont (staff) | PeopleAdmin | Atom feed (uvmjobs.com) | Highest-volume local source of program-coordinator/admin roles |
| Champlain College | Oracle Recruiting | Public JSON API | Melany's grad school; coordinator/advisor roles |
| Saint Michael's College | Oracle Recruiting | Public JSON API | Colchester; smaller but steady |
| City of Burlington | NeoGov | Server-rendered HTML (XHR trick) | Salaries always listed, many roles $60k+ |
| City of South Burlington | NeoGov | Same | Smaller volume |
| Town of Essex / Essex Junction | BambooHR | Public JSON API | Low admin volume, cheap to poll |

### Private sector & boards

| Employer | ATS | How we read it | Why it matters |
|---|---|---|---|
| Beta Technologies | Greenhouse | Public JSON API (salaries included!) | Fast-growing; ops/supply-chain/program coordination |
| OnLogic | Workable | Public JSON API | HR/ops roles occasionally |
| GlobalFoundries | Workday | Public JSON API | Largest private employer (Essex Junction); business-ops roles appear |
| National Life Group | Greenhouse | Public JSON API | Montpelier — outside commute range, only remote roles pass |
| EastRise Credit Union (ex-VSECU/NEFCU) | ADP Workforce Now | Public JSON API | Williston HQ; ops/analyst roles in range |
| NorthCountry FCU | JazzHR | HTML board scrape | Small volume |
| **Seven Days Jobs** | WP Job Manager | RSS feed (10 newest → daily polling matters) | THE local board; catches small employers with no ATS. ~100 postings/week |
| **Common Good Vermont** | WP Job Manager | WordPress REST API (company + salary metadata) | Statewide nonprofit board; program/admin roles |

## Watchlist (no clean feed — check by hand occasionally)

- **VSAC** (Winooski) — custom portal, ~1 posting at a time; great fit when open: https://www.vsac.org/careers
- **UVM Foundation** — Paycor; Program Coordinator roles at $60–85k appear: https://www.uvmfoundation.org/careers
- **Vermont Housing Finance Agency** — posts to Indeed; Program Operations Analyst-type roles: https://www.vhfa.org/careers
- **Age Well** (Essex Jct) — posts on Indeed only: https://www.indeed.com/cmp/Age-Well
- **United Way of NW VT** — PDF postings by email: https://unitedwaynwvt.org/get-involved/join-our-team/
- **Ben & Jerry's / Seventh Generation** — Unilever custom portal, hard to automate; their VT postings usually also hit Seven Days/LinkedIn: https://careers.unilever.com/location/vermont-united-states-jobs/34155/6252001-5242283/3
- **Vermont Federal Credit Union** — UKG but board ID not exposed; small volume: https://www.vermontfederal.org/careers
- **Vermont JobLink** (state DOL) — huge but noisy aggregator, no API; useful for manual searches: https://www.vermontjoblink.com
- **jobs.vcet.co** — curated Getro board of VT employers (tech-leaning)

## Deliberately not scraped

- **Indeed, LinkedIn, Glassdoor** — no public APIs, login walls, anti-bot measures, and their listings are mostly republished from the employer ATSes above (which we read directly, and earlier). Best used manually: set up a LinkedIn/Indeed email alert for "healthcare administration Burlington VT" as a safety net for one-off employers.
- **OneCare Vermont** — ceased operations Dec 31, 2025.

## Notes

- Vermont's pay-transparency law (Act 155, effective July 2024) requires pay
  ranges in most job ads from employers with 10+ employees, which is why pay
  parsing works as often as it does.
- ATS APIs used here are public but unofficial; any of them can change shape.
  A failed source shows up in the digest's "sources that failed" section
  rather than silently disappearing.
