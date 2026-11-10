"""Retailer pilot, step 3: fetch every product URL in a list, politely.

Run from the project root:
    python src/collect_listings.py data/alternate_urls.txt

One URL per line; blank lines and lines starting with # are ignored; duplicates are
fetched once. Each page is saved raw by fetch_one.fetch_and_save (page + provenance
record). Waits PAUSE_SECONDS between requests and stops if the shop starts refusing.
Afterwards run: python src/parse_listing.py
"""
import sys
import time

from fetch_one import clean_url, fetch_and_save

PAUSE_SECONDS = 5
MAX_REFUSALS = 3          # stop early instead of hammering a shop that says no


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python src/collect_listings.py data/alternate_urls.txt")
    lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
    urls = list(dict.fromkeys(clean_url(l) for l in lines
                              if l.strip() and not l.strip().startswith("#")))
    print(f"{len(urls)} distinct URLs; pausing {PAUSE_SECONDS}s between requests.")

    ok, refused = 0, 0
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}]")
        try:
            meta, _ = fetch_and_save(url)
        except Exception as err:          # network error: note it and move on
            print("  failed:", err)
            refused += 1
        else:
            if meta["http_status"] == 200:
                ok += 1
                print("  saved, HTTP 200")
            else:
                refused += 1
                print(f"  saved refusal, HTTP {meta['http_status']}")
        if refused >= MAX_REFUSALS:
            print(f"\nStopping: {refused} refusals or errors.")
            break
        if i < len(urls):
            time.sleep(PAUSE_SECONDS)

    print(f"\nDone: {ok} pages saved with HTTP 200, {refused} refused or failed.")


if __name__ == "__main__":
    main()
