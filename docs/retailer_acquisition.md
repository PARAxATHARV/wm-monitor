# Retailer data acquisition: what was checked, and what was not

Status on 10 Nov 2026. Retailer pilot only (Step 7). The EPREL analysis does not depend on
any retailer data.

## Bottom line

- **Technically reachable:** yes for Alternate. 28 page requests returned HTTP 200
  (26 product pages, the homepage, and one duplicate product page), and all 26 product
  sheets (PDF) were downloaded.
- **Permission:** **not established.** Reachable pages are not the same as permission to
  collect them systematically. Alternate's full robots.txt rules, its Nutzungsbedingungen
  and its Impressum were not reviewed, and nobody at Alternate was asked. No collection
  beyond this 26-listing pilot should happen until that is clarified (ideally with
  Fraunhofer ISI's guidance on retailer data).

## What exists as evidence

| Item | Evidence in this folder | What it shows | What it does not show |
|---|---|---|---|
| Shop survey, 9 shops | `check_shops.sh`, `shops_check.txt` | Homepage HTTP status, visible bot-protection markers, and robots.txt lines filtered to `User-agent: *`, a full-site `Disallow: /`, and `Crawl-delay` | Path-specific robots rules; terms of use |
| Alternate robots.txt | `shops_check.txt` (filtered lines only) | Has a `User-agent: *` group and no full-site `Disallow: /` and no `Crawl-delay` line | Whether product or `/html/` paths are disallowed. The full file was not saved or read |
| Alternate terms (AGB) | Manual keyword search by Atharv, not saved | The AGB found only clause 2.10 (automated order e-mails, unrelated); no hits for crawler, robot, scraping or Datenbank | The AGB govern purchases. Nutzungsbedingungen and Impressum were not checked |
| Alternate product pages | `data/raw/alternate/*.html` + `.json` | 28 responses, all HTTP 200, 10 Nov 2026 10:28 to 10:56 UTC, with URL, time, status, size, SHA-256 and user agent `Mozilla/5.0 (research pilot; wm-monitor)`; 5 s pause between requests | Permission |
| Product sheets (PDF) | `data/raw/alternate/datasheets/*.pdf` + `.json` | 26 files from `assets.tlecdn.net`, 10 Nov 2026 11:11 to 11:13 UTC, URL, time, size and SHA-256 recorded; 3 s pause | The CDN host's robots.txt and terms were not checked |
| Otto | `data/raw/otto/2026-11-10T10-03-51Z_2117257074.*` | Product page answered HTTP 400 with a Kasada bot-protection script | — |
| Otto robots.txt | Pasted in chat on 10 Nov, **not saved** | For `*` it listed only a few disallowed paths (/gate/, /onex/, /cdn-cgi/) | Not reproducible from files; terms keyword search found nothing relevant |

## Decisions taken

- **Otto:** not used. Its product pages sit behind bot protection. Getting past it would
  bypass an access control, so it was not attempted.
- **Survey of other shops** (`shops_check.txt`):
  - Euronics, Cyberport, Galaxus, notebooksbilliger, Conrad: blocked or challenged at the homepage.
  - Saturn: robots.txt has full-site `Disallow: /` lines (which user agents they apply to was not checked) and the homepage shows challenge markers.
  - Expert: `Disallow: /` for `*`.
  - AO: only a redirect was checked.
- **Alternate:** used for the 26-listing pilot only, at a slow rate with an identifying
  user agent. The listing URLs came from `data/alternate_urls.txt`. No further collection
  has been done since.

## Open before any further collection

1. Save and read Alternate's full robots.txt, and check the pilot paths against it.
2. Read Alternate's Nutzungsbedingungen and Impressum for rules on automated access or reuse of data.
3. Check robots.txt for `assets.tlecdn.net`.
4. Ask Fraunhofer ISI whether to use a retailer agreement, a data provider, or manual
   sampling instead.
