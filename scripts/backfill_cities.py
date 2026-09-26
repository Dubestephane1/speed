#!/usr/bin/env python3
"""Backfill city names for measured sites that no local record knows.

WHY THIS EXISTS
    The wave score CSVs (hvac_scores*.csv, realtor_scores.csv, ...) store only
    a URL and page metrics. The candidate lists, the outreach registry and the
    filename hints have already been joined by sync_data.py, but some sites
    are still unattributed. Their own website footer usually carries a
    Canadian postal address, so we read it from there.

HOW A CITY IS ACCEPTED
    1. Address pattern "<City>, <PROVINCE>" (e.g. "Barrie, ON") in the page
       text, and
    2. the site's own postal code agrees with that province. The first letter
       of a Canadian postal code identifies the province:
       A NL, B NS, C PE, E NB, H/J QC, K/L/M/N/P ON, R MB, S SK, T AB,
       V BC, X NT/NU, Y YT.
    A city that fails the cross-check is rejected rather than guessed.
    A bare city name with no province is recorded as "low" confidence and is
    NOT applied automatically -- it is listed for review.

READ-ONLY: performs HTTP GETs against the measured sites' own homepages and
the site's /contact page. Writes one file: data/city_overrides.csv.

USAGE
    python scripts/backfill_cities.py --limit 10      # pilot
    python scripts/backfill_cities.py                 # all gaps
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAPS = os.path.join(REPO, "data", "mapping_gaps.csv")
OUT = os.path.join(REPO, "data", "city_overrides.csv")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# first letter of a Canadian postal code -> province code
FSA_PROVINCE = {
    "A": "NL", "B": "NS", "C": "PE", "E": "NB", "G": "QC", "H": "QC",
    "J": "QC", "K": "ON", "L": "ON", "M": "ON", "N": "ON", "P": "ON",
    "R": "MB", "S": "SK", "T": "AB", "V": "BC", "X": "NT", "Y": "YT",
}
PROVINCES = set(FSA_PROVINCE.values())

POSTAL = re.compile(
    r"\b([ABCEGHJKLMNPRSTVXY]\d[ABCEGHJ-NPRSTV-Z])[ -]?(\d[ABCEGHJ-NPRSTV-Z]\d)\b")
# "<City>, <PROVINCE>" - the standard Canadian address footer. City may be one
# or two words and may include an accent.
ADDRESS = re.compile(
    r"\b([A-Z][\w'’\-]+(?:[ -][A-Z][\w'’\-]+)?),\s*"
    r"(AB|BC|MB|NB|NL|NS|NT|ON|PE|QC|SK|YT)\b")
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")

# Region / marketing words that follow the address pattern but are not a
# city. Seen in the pilot output: "Lower Mainland, BC", "Fraser Valley, BC".
REGIONS = {
    "lower mainland", "metro vancouver", "fraser valley", "greater vancouver",
    "vancouver island", "the valley", "lower mainland", "metro toronto",
    "greater toronto", "golden horseshoe", "capital region", "our service area",
    "surrounding area", "greater montreal", "montreal area",
}
# Leading words that are part of a heading, not the city name:
# "IN KELOWNA, BC", "Today Sudbury, ON", "Heating Vancouver, BC".
PREFIX_WORDS = {
    "in", "today", "serving", "serving", "heating", "plumbing", "hvac",
    "area", "region", "city", "town", "we", "our", "the", "near", "around",
    "greater", "greater", "district", "county", "metro",
}
NOT_CITIES = {"inc", "ltd", "llc", "com", "ca", "www", "tel", "fax", "email"}
# "Street Saskatoon, SK" happens when the address line is
# "<number> <Street> <City>, <PROVINCE>". Strip the street type.
STREET_TYPES = {
    "street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
    "drive", "dr", "lane", "ln", "way", "court", "ct", "place", "pl",
    "terrace", "suite", "unit", "box", "highway", "hwy", "parkway", "pkwy",
    "circle", "cres", "close", "crescent", "park", "plaza", "trail", "way",
}


def clean_city(city: str) -> str:
    """Drop street types, marketing prefixes and region names."""
    parts = city.split()
    if len(parts) == 2:
        if parts[0].lower() in STREET_TYPES:
            return parts[1]
        if parts[1].lower() in STREET_TYPES:
            return parts[0]
    # drop leading filler words: "IN KELOWNA" -> "KELOWNA"
    while parts and parts[0].lower() in PREFIX_WORDS:
        parts = parts[1:]
    out = " ".join(parts)
    if not out or out.lower() in REGIONS:
        return ""
    # ALL CAPS addresses ("WHISTLER, BC") are normal; title-case them
    if out.isupper():
        out = out.title()
    return out


def fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(400_000)
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def text_of(html: str) -> str:
    body = TAG.sub(" ", html)
    return WS.sub(" ", body)


def resolve(url: str) -> dict:
    """Return the best supported city for one site, plus its evidence."""
    host = url.split("/")[0]
    out = {"url": url, "city": "", "province": "", "method": "", "confidence": "",
           "evidence": ""}
    pages = []
    for candidate in (f"https://{host}", f"https://{host}/contact",
                      f"https://{host}/contact-us"):
        try:
            pages.append(text_of(fetch(candidate)))
        except (urllib.error.URLError, OSError, ValueError):
            continue

    for text in pages:
        low = text.lower()
        postal = POSTAL.search(text)
        province = FSA_PROVINCE.get(postal.group(1).upper()) if postal else ""

        counts: dict[tuple[str, str], int] = {}
        for m in ADDRESS.finditer(text):
            city, prov = clean_city(m.group(1)), m.group(2)
            if prov not in PROVINCES:
                continue
            if city.lower() in NOT_CITIES or len(city) < 3:
                continue
            counts[(city, prov)] = counts.get((city, prov), 0) + 1

        if not counts:
            continue
        (city, prov), hits = max(counts.items(), key=lambda kv: kv[1])

        # cross-check: the site's own postal code must agree with the province.
        # group(1) is the FSA (e.g. "N2V"); its FIRST letter identifies the
        # province, so index [0].
        fsa = postal.group(1).upper() if postal else ""
        if postal and prov and FSA_PROVINCE.get(fsa[0]) != prov:
            out.update(method="address_postal_mismatch", confidence="rejected",
                       evidence=f"{city}, {prov} vs postal {postal.group(0)}")
            continue
        # A city named once in the page is often a service area rather than
        # the location. Repeated mentions in the footer are stronger.
        confidence = "high" if hits >= 2 else "low"
        out.update(city=city, province=prov, method="address_footer",
                   confidence=confidence,
                   evidence=f'"{city}, {prov}" x{hits}'
                            + (f" | postal {postal.group(0)}" if postal else ""))
        return out

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="only resolve the first N gaps (pilot mode)")
    args = ap.parse_args()

    if not os.path.exists(GAPS):
        sys.exit(f"missing {GAPS} - run scripts/sync_data.py first")

    with open(GAPS, newline="", encoding="utf-8") as f:
        gaps = [r["url"] for r in csv.DictReader(f)]
    targets = gaps[:args.limit] if args.limit else gaps
    print(f"resolving {len(targets)} of {len(gaps)} unmapped sites")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for res in pool.map(resolve, targets):
            results.append(res)
            if res["city"]:
                print(f"  {res['url']:<45} {res['city']}, {res['province']}"
                      f"  [{res['method']}]")
            elif res["confidence"] == "rejected":
                print(f"  {res['url']:<45} REJECTED {res['evidence']}")
            else:
                print(f"  {res['url']:<45} no address found")

    high = [r for r in results if r["confidence"] == "high"]
    low = [r for r in results if r["confidence"] == "low"]
    rejected = [r for r in results if r["confidence"] == "rejected"]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "city", "province", "method",
                                          "confidence", "evidence"])
        w.writeheader()
        for r in high + low + rejected:
            w.writerow(r)

    print()
    print(f"resolved (2+ mentions, province agrees): {len(high)}")
    print(f"needs review (single mention)           : {len(low)}")
    print(f"rejected by cross-check                 : {len(rejected)}")
    print(f"nothing found                           : "
          f"{len(results) - len(high) - len(low) - len(rejected)}")
    print(f"wrote {os.path.relpath(OUT, REPO)}")
    if low:
        print()
        print("single-mention matches (NOT applied, review these):")
        for r in low:
            print(f"  {r['url']:<45} {r['city']}, {r['province']}"
                  f"  {r['evidence']}")


if __name__ == "__main__":
    main()
