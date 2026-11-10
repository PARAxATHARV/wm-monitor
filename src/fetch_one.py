"""Retailer pilot, step 1: fetch ONE product page and save the raw response.

Run from the project root:
    python src/fetch_one.py "<product URL>"

Saves, without changing anything:
    data/raw/<shop>/<collected_at>_<page_id>.html   the raw page (or the refusal)
    data/raw/<shop>/<collected_at>_<page_id>.json   URL, time, status, size, SHA-256
Then prints a quick look at what the page contains (no parsing is stored yet).
"""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
USER_AGENT = "Mozilla/5.0 (research pilot; wm-monitor)"


def clean_url(url):
    url = url.strip()
    md = re.search(r"\]\((https?://[^)]+)\)", url)   # chat apps sometimes paste [text](url)
    if md:
        url = md.group(1)
    return url.split("#")[0]                 # drop the #... part, it is browser-only


def fetch_and_save(url):
    """Fetch one URL, save the raw body and a provenance record, return (meta, html)."""
    url = clean_url(url)
    print("Fetching:", url)
    shop = urlparse(url).netloc.removeprefix("www.")
    out_dir = RAW_DIR / shop.split(".")[0]
    m = re.search(r"(?:-|/product/)([A-Za-z0-9]{6,12})/?$", url.rstrip("/") + "/")
    page_id = m.group(1) if m else "unknown"

    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept-Language": "de-DE,de;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            final_url = resp.geturl()
            body = resp.read()
    except urllib.error.HTTPError as err:   # keep the refusal as evidence too
        status = err.code
        final_url = err.geturl()
        body = err.read()
        print(f"Server answered HTTP {status}; saving that response anyway.")

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{collected_at}_{page_id}"
    (out_dir / f"{stem}.html").write_bytes(body)
    meta = {
        "source": shop,
        "url": url,
        "final_url": final_url,
        "page_id": page_id,
        "collected_at_utc": collected_at,
        "http_status": status,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "user_agent": USER_AGENT,
    }
    (out_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta, body.decode("utf-8", errors="replace")


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: python src/fetch_one.py "<product URL>"')
    meta, html = fetch_and_save(sys.argv[1])
    pdfs = sorted(set(re.findall(r"https?://[^\"'\s<>]+?\.pdf", html)))
    eprel = sorted(set(re.findall(r"eprel\.ec\.europa\.eu/[^\"'\s<>]*?(\d{5,8})", html)))
    print(json.dumps(meta, indent=2))
    print("JSON-LD blocks:", html.count("application/ld+json"))
    print("EPREL IDs linked on the page:", eprel or "none")
    print("PDF links:", len(pdfs))
    for p in pdfs:
        print("  ", p)
    for word in ["kasada", "kpsdk", "captcha", "challenge-platform"]:
        if word in html.lower():
            print("WARNING: bot-protection marker found:", word)
    for word in ["gtin", "ean", "mpn", "price", "availability"]:
        print(f"'{word}' appears", html.lower().count(f'"{word}'), "times")


if __name__ == "__main__":
    main()
