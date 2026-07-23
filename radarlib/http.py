"""Small HTTP helper on top of the standard library (no external dependencies)."""

import gzip
import json
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 job-radar/1.0 (personal use)"
)

# Be polite: small pause between requests to the same host.
_last_request_at: dict[str, float] = {}
POLITE_DELAY_SECONDS = 1.0


def _throttle(url: str) -> None:
    host = url.split("/")[2]
    elapsed = time.monotonic() - _last_request_at.get(host, 0.0)
    if elapsed < POLITE_DELAY_SECONDS:
        time.sleep(POLITE_DELAY_SECONDS - elapsed)
    _last_request_at[host] = time.monotonic()


def fetch(url: str, *, post_json: dict | None = None, headers: dict | None = None,
          timeout: int = 30, retries: int = 2) -> bytes:
    """GET (or POST JSON) a URL, with retries and gzip handling."""
    _throttle(url)
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "Accept-Encoding": "gzip",
    }
    if headers:
        req_headers.update(headers)
    data = None
    if post_json is not None:
        data = json.dumps(post_json).encode()
        req_headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last_error = err
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed for {url}: {last_error}")


def fetch_json(url: str, **kwargs) -> dict | list:
    return json.loads(fetch(url, **kwargs).decode("utf-8", errors="replace"))


def fetch_text(url: str, **kwargs) -> str:
    return fetch(url, **kwargs).decode("utf-8", errors="replace")
