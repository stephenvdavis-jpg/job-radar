# Burlington VT job radar

A tiny job tracker for Melany's move to the Burlington, Vermont area. Every
day it reads ~23 public job sources (hospital career sites, the State of
Vermont, UVM, local boards — see [SOURCES.md](SOURCES.md)), keeps a running
database of every listing, and writes a digest sorted into:

- ⭐ **Best matches** — healthcare-admin fit (MHA-appropriate), commutable or
  remote, meets the $25/hr (~$52k/yr) pay floor where pay is listed
- 👀 **Still open, worth a look** — decent business/admin fit or missing info
- 🗑 **Probably skip** — wrong field, needs a license she doesn't have, too
  far, or pays under $25/hr (kept collapsed, with the reason)

It also tracks change over time: new listings, listings that closed, and how
long each has been posted. Pure Python standard library — nothing to install.

## Run it locally

```bash
python3 radar.py run --open   # fetch everything, then open the digest
python3 radar.py sources      # list sources and how many jobs each has
python3 radar.py test uvmmc   # try one source and see what it returns
```

The latest digest is always [digests/latest.md](digests/latest.md); dated
copies accumulate alongside it. The database is `data/jobs.json`.

## Run it automatically (GitHub Actions)

Push this repo to GitHub (private is fine) and it runs every morning at
7 AM Eastern via `.github/workflows/radar.yml`, committing the updated
digest back to the repo. Reading `digests/latest.md` on github.com is the
easiest way to check it from any device — no setup on Melany's side beyond
being added to the repo.

To trigger a run manually: repo → Actions → "Daily job radar" → Run workflow.

## Tuning

- **Add/remove employers**: edit `sources.json` (set `"enabled": false` to
  pause one).
- **Matching rules**: edit `radarlib/match.py` — the keyword lists
  (strong/good/exclude), the commutable-towns list, and the $25/hr floor all
  live at the top of the file.
- If a "best match" is wrong (or a good job landed in "skip"), tweak the
  keywords; the next run re-scores everything.

## Honest limitations

- Pay isn't listed for every job. Unlisted pay never disqualifies a job —
  it's just flagged "pay not listed."
- Seven Days' feed only exposes the 10 newest postings, so the radar catches
  its listings only as long as it runs daily.
- These are unofficial public APIs; when one changes shape the digest lists
  the failure under "sources that failed" instead of hiding it.
- A few small employers have no feed at all — see the watchlist in
  [SOURCES.md](SOURCES.md) for the short manual-check list.
