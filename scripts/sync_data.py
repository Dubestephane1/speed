"""Consolidate scattered per-wave score CSVs into one census file per country.

WHY THIS EXISTS
    The site published 788 Canadian sites that were measured across ~70
    throwaway wave files (tmp/*_scores*.csv, _archive/**). No single file held
    the census, so every number on the site was hand-edited and went stale.
    This script is the "sync step" from option_a_generator_plan.md: it folds
    every measurement we have into data/<country>/<country>_all.csv.

RULES
    - One row per URL. Duplicates keep the NEWEST measurement (file mtime).
    - Never invent a city or niche. Missing stays "unknown" and is written to
      data/mapping_gaps.csv so the hole is visible and fixable, not hidden.
    - Failed measurements (empty perf + error) are kept: they are real data
      and the "fail rate" figure depends on them.

USAGE
    python scripts/sync_data.py            # write data/*.csv
    python scripts/sync_data.py --check    # print summary, write nothing
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ODIN_TMP = r"D:\Docs\Odin_Mod\tmp"
ARCHIVE = r"C:\Users\dubes\AppData\Local\Temp\opencode"
ARCHIVE2 = r"C:\Users\dubes\AppData\Local\Temp\opencode\_archive"
HUGINN_US = r"D:\Docs\Huginn\data\us"

OUT_COLUMNS = [
    "url", "country", "city", "city_source", "niche", "platform", "perf", "a11y",
    "best_practices", "seo", "LCP_ms", "CLS", "TBT_ms", "FCP_ms", "bytes",
    "load_category", "error", "measured_at", "source_file",
]

# ---------------------------------------------------------------------------
# Source registry. (glob, country, niche, city)
#
# niche/city are "" when the file name does not prove them. A file name that
# DOES prove them sets them here instead of guessing later. Anything left
# unknown lands in mapping_gaps.csv.
#
# Documented inferences (auditable on purpose, not silent):
#   misc/rn_ps.csv -> dental, Winnipeg. The only row is renewdentalwpg.com
#   ("wpg" = Winnipeg); confirmed by reading the file, not guessed at scale.
# ---------------------------------------------------------------------------
SOURCES: list[tuple[str, str, str, str]] = [
    # ---- Canada: current working waves (Odin_Mod/tmp) ---------------------
    (os.path.join(ODIN_TMP, "physio_scores*.csv"), "CA", "physio", ""),
    (os.path.join(ODIN_TMP, "hvac_scores*.csv"), "CA", "hvac", ""),
    (os.path.join(ODIN_TMP, "realtor_scores.csv"), "CA", "realtor", ""),
    (os.path.join(ODIN_TMP, "toronto_batch2_scores.csv"), "CA", "dental", "Toronto"),
    # per-city dental waves (dentiste*.ca confirmed dental by reading rows)
    (os.path.join(ODIN_TMP, "quebec_scores*.csv"), "CA", "dental", "Quebec"),
    (os.path.join(ODIN_TMP, "sherbrooke_scores*.csv"), "CA", "dental", "Sherbrooke"),
    (os.path.join(ODIN_TMP, "blainville_scores*.csv"), "CA", "dental", "Blainville"),
    (os.path.join(ODIN_TMP, "mississauga_scores*.csv"), "CA", "dental", "Mississauga"),
    (os.path.join(ODIN_TMP, "gatineau_scores*.csv"), "CA", "dental", "Gatineau"),
    (os.path.join(ODIN_TMP, "longueuil_scores*.csv"), "CA", "dental", "Longueuil"),
    (os.path.join(ODIN_TMP, "levis_realtor_scores.csv"), "CA", "realtor", "Levis"),
    # ---- Canada: archived waves (the missing ~111+ sites) -----------------
    (os.path.join(ARCHIVE2, "dental_wave_raw", "*.csv"), "CA", "dental", ""),
    (os.path.join(ARCHIVE2, "opt_wave_raw", "opt_scores.csv"), "CA", "optometrist", ""),
    (os.path.join(ARCHIVE2, "opt_wave_raw", "opt_leads.csv"), "CA", "optometrist", ""),
    (os.path.join(ARCHIVE2, "realtor_wave_raw", "realtor_scores.csv"), "CA", "realtor", ""),
    (os.path.join(ARCHIVE2, "misc", "rn_ps.csv"), "CA", "dental", "Winnipeg"),
    (os.path.join(ARCHIVE, "opt_data.csv"), "CA", "optometrist", ""),
    # ---- United States (clone output; city/country/niche already present) --
    (os.path.join(HUGINN_US, "*_us_scores.csv"), "US", "", ""),
]

# City per-city wave overrides, applied by filename match (lowercased).
# Only where the file name itself states the city.
CITY_BY_TOKEN = {
    "calgary": "Calgary", "edmonton": "Edmonton", "ottawa": "Ottawa",
    "toronto": "Toronto", "vancouver": "Vancouver", "windsor": "Windsor",
    "winnipeg": "Winnipeg", "sherbrooke": "Sherbrooke",
    "blainville": "Blainville", "gatineau": "Gatineau",
    "mississauga": "Mississauga", "levis": "Levis",
    "longueuil": "Longueuil", "quebec": "Quebec",
}

# URL -> (city, niche) harvested from candidate/lead files that carry them.
MAPPING_SOURCES = [
    os.path.join(ODIN_TMP, "*candidates*.csv"),
    os.path.join(ODIN_TMP, "*_qualifying*.csv"),
    os.path.join(ODIN_TMP, "*emails_final.csv"),
    r"D:\Docs\Odin_Mod\data\realtor_leads.csv",
    # our own outreach records: website -> city, authoritative (253 rows)
    r"D:\Docs\Odin_Mod\data\outreach_registry.csv",
    os.path.join(ARCHIVE, "opt_data.csv"),
    os.path.join(ARCHIVE2, "opt_wave_raw", "opt_leads.csv"),
]

# City tokens matched inside a domain name, used ONLY when no record above
# knows the city. This is inference from evidence (the domain literally names
# the place), not a guess: "banffrealestate.com" -> Banff. Every row filled
# this way is marked city_source=domain_token so it can be audited or undone.
#
# Minimum 5 characters: shorter tokens match by accident inside ordinary
# words ("nl", "bc", "on" are province codes, not cities). A domain that
# contains two different city tokens is left unmapped rather than guessed.
CITY_TOKENS = {
    "banff": "Banff", "hamilton": "Hamilton", "sudbury": "Sudbury",
    "vancouver": "Vancouver", "calgary": "Calgary", "winnipeg": "Winnipeg",
    "toronto": "Toronto", "ottawa": "Ottawa", "edmonton": "Edmonton",
    "quebec": "Quebec", "montreal": "Montreal", "victoria": "Victoria",
    "halifax": "Halifax", "mississauga": "Mississauga", "oshawa": "Oshawa",
    "brampton": "Brampton", "kitchener": "Kitchener", "laval": "Laval",
    "gatineau": "Gatineau", "longueuil": "Longueuil",
    "sherbrooke": "Sherbrooke", "reddeer": "Red Deer", "nanaimo": "Nanaimo",
    "kelowna": "Kelowna", "abbotsford": "Abbotsford", "windsor": "Windsor",
    "sarnia": "Sarnia", "chatham": "Chatham", "kingston": "Kingston",
    "guelph": "Guelph", "barrie": "Barrie", "peterborough": "Peterborough",
    "saintjohn": "Saint John", "moncton": "Moncton",
    "saguenay": "Saguenay", "thunderbay": "Thunder Bay",
    "steinbach": "Steinbach", "miramichi": "Miramichi",
    "charlottetown": "Charlottetown", "truro": "Truro",
    "summerside": "Summerside", "amherst": "Amherst",
    " Medicinehat": "Medicine Hat", "canmore": "Canmore",
    "brandon": "Brandon", "winkler": "Winkler", "selkirk": "Selkirk",
    "swiftcurrent": "Swift Current", "princealbert": "Prince Albert",
    "yellowknife": "Yellowknife", "whitehorse": "Whitehorse",
    "lethbridge": "Lethbridge", " Medicine-hat": "Medicine Hat",
    "airdrie": "Airdrie", "redrock": "Red Rock", "kamloops": "Kamloops",
    "chilliwack": "Chilliwack", "portland": "Portland", "fredericton": "Fredericton",
    "saintjohns": "Saint John's", "stjohns": "Saint John's",
}


def city_from_domain(url: str) -> str:
    """Return a city only when exactly one known token appears in the domain."""
    host = url.split("/")[0]
    hits = {city for token, city in CITY_TOKENS.items() if token in host}
    return hits.pop() if len(hits) == 1 else ""

URL_KEYS = ("url", "website", "site", "domain")
CITY_KEYS = ("city", "town", "ville")
NICHE_KEYS = ("niche", "category", "industry", "type")
PERF_KEYS = ("perf", "score", "performance", "perf_score")


def norm_url(u: str) -> str:
    """Canonical key for dedupe: scheme-less, lower-case, no trailing slash."""
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def pick(row: dict, keys: tuple[str, ...]) -> str:
    low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for k in keys:
        if low.get(k):
            return low[k]
    return ""


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def city_from_filename(path: str) -> str:
    low = os.path.basename(path).lower()
    for token, city in CITY_BY_TOKEN.items():
        if token in low:
            return city
    return ""


def load_url_map() -> dict[str, tuple[str, str]]:
    """url -> (city, niche) from candidate/lead files. First non-empty wins."""
    url_map: dict[str, tuple[str, str]] = {}
    for pattern in MAPPING_SOURCES:
        for path in sorted(glob.glob(pattern)):
            try:
                rows = read_csv(path)
            except OSError:
                continue
            for row in rows:
                u = norm_url(pick(row, URL_KEYS))
                if not u:
                    continue
                city = pick(row, CITY_KEYS)
                niche = pick(row, NICHE_KEYS).lower()
                prev_city, prev_niche = url_map.get(u, ("", ""))
                url_map[u] = (prev_city or city, prev_niche or niche)
    return url_map


def load_research_map() -> dict[str, tuple[str, str]]:
    """url -> (city, city_source) from data/city_overrides.csv, verified rows.

    Produced by scripts/backfill_cities.py, which reads the address out of the
    site's own footer and cross-checks the province against the site's postal
    code, and by scripts/approve_overrides.py, which records a human approving
    the single-mention bucket. Applied buckets:

        high      2+ mentions, province agrees with the postal code
        approved  reviewed and approved by Stephane (see approved_by)

    "rejected" rows stay in the file as evidence of a wrong match and are
    never applied. The bucket is carried through as city_source so a reader of
    the CSV can still tell machine-verified from human-approved.
    """
    path = os.path.join(REPO, "data", "city_overrides.csv")
    if not os.path.exists(path):
        return {}
    out: dict[str, tuple[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bucket = (row.get("confidence") or "").strip()
            if bucket not in ("high", "approved"):
                continue
            u = norm_url(row.get("url", ""))
            city = (row.get("city") or "").strip()
            if u and city:
                out[u] = (city, "research" if bucket == "high" else "approved")
    return out


def collect() -> tuple[dict[str, dict], dict[str, tuple[str, str]]]:
    """Fold every source into {url: row}. Newest file wins on conflict."""
    url_map = load_url_map()
    research = load_research_map()
    sites: dict[str, dict] = {}
    files_read = 0

    for pattern, country, niche_hint, city_hint in SOURCES:
        for path in sorted(glob.glob(pattern)):
            try:
                rows = read_csv(path)
            except OSError as exc:
                print(f"  ! unreadable {path}: {exc}", file=sys.stderr)
                continue
            files_read += 1
            fname_niche = niche_hint
            fname_city = city_hint or city_from_filename(path)
            mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)

            for row in rows:
                u = norm_url(pick(row, URL_KEYS))
                if not u or "." not in u:
                    continue

                map_city, map_niche = url_map.get(u, ("", ""))
                research_city, research_src = research.get(u, ("", ""))
                row_city = pick(row, CITY_KEYS)
                if row_city:
                    city, city_src = row_city, "row"
                elif map_city:
                    city, city_src = map_city, "map"
                elif research_city:
                    city, city_src = research_city, research_src
                elif fname_city:
                    city, city_src = fname_city, "filename"
                else:
                    city = city_from_domain(u)
                    city_src = "domain_token" if city else "unmapped"
                niche = (pick(row, NICHE_KEYS).lower() or map_niche
                         or fname_niche or "unknown")
                if country == "US":
                    # US pipeline states these explicitly; trust the row.
                    city = pick(row, CITY_KEYS) or "unknown"
                    city_src = "row" if pick(row, CITY_KEYS) else "unmapped"
                    niche = pick(row, NICHE_KEYS).lower() or "unknown"
                    country_val = "US"
                else:
                    country_val = "Canada"

                rec = {
                    "url": u,
                    "country": country_val,
                    "city": city or "unknown",
                    "city_source": city_src or "unmapped",
                    "niche": niche or "unknown",
                    "platform": pick(row, ("platform", "cms")),
                    "perf": pick(row, PERF_KEYS),
                    "a11y": pick(row, ("a11y", "accessibility")),
                    "best_practices": pick(row, ("best_practices",)),
                    "seo": pick(row, ("seo",)),
                    "LCP_ms": pick(row, ("lcp_ms", "lcp")),
                    "CLS": pick(row, ("cls",)),
                    "TBT_ms": pick(row, ("tbt_ms", "tbt")),
                    "FCP_ms": pick(row, ("fcp_ms", "fcp")),
                    "bytes": pick(row, ("bytes", "transfer_size")),
                    "load_category": pick(row, ("load_category",)),
                    "error": pick(row, ("error",)),
                    "measured_at": mtime.strftime("%Y-%m-%d"),
                    "source_file": os.path.basename(path),
                    "_mtime": mtime,
                }
                prev = sites.get(u)
                if prev is None or rec["_mtime"] >= prev["_mtime"]:
                    sites[u] = rec

    return sites, url_map


def write_outputs(sites: dict[str, dict], check_only: bool) -> None:
    by_country: dict[str, list[dict]] = {}
    for rec in sites.values():
        by_country.setdefault(rec["country"], []).append(rec)

    targets = {"Canada": "canada", "US": "united-states"}
    summary = {}

    for country, slug in targets.items():
        rows = sorted(by_country.get(country, []),
                      key=lambda r: (r["city"], r["niche"], r["url"]))
        scored = [r for r in rows if r["perf"].isdigit()]
        failed = [r for r in rows if not r["perf"].isdigit()]
        cities = {r["city"] for r in rows if r["city"] != "unknown"}
        niches = {r["niche"] for r in rows if r["niche"] != "unknown"}
        avg = round(sum(int(r["perf"]) for r in scored) / len(scored), 1) if scored else 0
        red = sum(1 for r in scored if int(r["perf"]) < 50)
        green = sum(1 for r in scored if int(r["perf"]) >= 90)

        summary[country] = {
            "rows": len(rows), "scored": len(scored), "failed": len(failed),
            "avg": avg, "red": red, "green": green,
            "cities": len(cities), "niches": sorted(niches),
            "unknown_city": sum(1 for r in rows if r["city"] == "unknown"),
            "unknown_niche": sum(1 for r in rows if r["niche"] == "unknown"),
            "city_source": {src: sum(1 for r in rows if r["city_source"] == src)
                            for src in ("row", "map", "research", "approved",
                                                 "filename", "domain_token", "unmapped")},
        }

        if check_only:
            continue
        out_dir = os.path.join(REPO, "data", slug)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{slug}_all.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=OUT_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"  wrote {os.path.relpath(out_path, REPO)}  ({len(rows)} rows)")

    # Gaps worklist: the honest to-do list for the next data pass.
    if not check_only:
        gaps = [r for r in sites.values()
                if r["city"] == "unknown" or r["niche"] == "unknown"]
        gaps.sort(key=lambda r: (r["country"], r["city"], r["url"]))
        gap_path = os.path.join(REPO, "data", "mapping_gaps.csv")
        os.makedirs(os.path.dirname(gap_path), exist_ok=True)
        with open(gap_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["url", "country", "city", "niche", "missing",
                         "city_source", "source_file"])
            for r in gaps:
                missing = ",".join(
                    x for x in ("city", "niche")
                    if r[x] == "unknown")
                w.writerow([r["url"], r["country"], r["city"], r["niche"],
                            missing, r["city_source"], r["source_file"]])
        print(f"  wrote data/mapping_gaps.csv  ({len(gaps)} rows)")

    print()
    for country, s in summary.items():
        print(f"== {country} ==")
        print(f"  rows (unique urls) : {s['rows']}")
        print(f"  scored            : {s['scored']}")
        print(f"  failed            : {s['failed']}  "
              f"({round(100 * s['failed'] / s['rows']) if s['rows'] else 0}% fail rate)")
        print(f"  avg perf          : {s['avg']}")
        print(f"  red (<50)         : {s['red']}")
        print(f"  green (>=90)      : {s['green']}")
        print(f"  cities known      : {s['cities']}")
        print(f"  niches            : {', '.join(s['niches'])}")
        print(f"  unknown city      : {s['unknown_city']}")
        print(f"  unknown niche     : {s['unknown_niche']}")
        print("  city came from    : " + ", ".join(
            f"{k}={v}" for k, v in s["city_source"].items() if v))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="print summary without writing files")
    args = ap.parse_args()

    sites, _url_map = collect()
    print(f"unique urls collected: {len(sites)}")
    write_outputs(sites, args.check)


if __name__ == "__main__":
    main()
