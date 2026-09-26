"""Build the site atlas from the census CSVs. No hand-written numbers.

WHY THIS EXISTS
    Every number on speed.stephanedube.dev used to be typed by hand and went
    stale (650 -> 788, 46 -> 50 cities, red 327 -> 329). This script reads
    data/<country>/<country>_all.csv, computes one aggregate, and renders every
    number from it. If the data changes, the site changes with it.

RULES (from option_a_generator_plan.md)
    1. A city is rankable only with >= MIN_RANKABLE scored sites. Smaller
       samples appear in a labelled "sampling in progress" note, never ranked.
    2. Numbers come only from this script. Templates hold prose and structure.
    3. Commentary is generated from each page's own data, or not emitted.
    4. English only.
    5. Review the diff, then push. This script never deploys.

USAGE
    python scripts/generate.py                  # render to build/ (staging)
    python scripts/generate.py --out site       # render over the live pages
    python scripts/generate.py --check          # print numbers + drift only
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import statistics
import sys
import unicodedata
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RED_MAX = 50        # score < 50 counts as red
GREEN_MIN = 90      # score >= 90 counts as green
MIN_RANKABLE = 10   # hard rule 1: fewer scored sites -> not rankable
MIN_NICHE_N = 5     # below this a niche cannot be called fastest/slowest

COUNTRY_LABEL = {"Canada": "Canada", "US": "United States"}
COUNTRY_SLUG = {"Canada": "canada", "US": "united-states"}
NICHE_LABEL = {
    "dental": "Dental", "hvac": "HVAC", "optometrist": "Optometry",
    "physio": "Physiotherapy", "realtor": "Real estate", "unknown": "Unclassified",
}
SITE = "https://speed.stephanedube.dev"


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_country(slug: str) -> list[dict]:
    path = os.path.join(REPO, "data", slug, f"{slug}_all.csv")
    if not os.path.exists(path):
        sys.exit(f"missing {path} - run scripts/sync_data.py first")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["perf_i"] = int(r["perf"]) if r["perf"].isdigit() else None
    return rows


def slugify(name: str) -> str:
    """'Trois-Rivières' -> 'trois-rivieres'. Accent-safe for URLs."""
    norm = unicodedata.normalize("NFKD", name)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
def stats(rows: list[dict]) -> dict:
    """Everything the templates need for one group of sites."""
    scored = [r for r in rows if r["perf_i"] is not None]
    total = len(rows)
    n = len(scored)
    scores = [r["perf_i"] for r in scored]
    red = sum(1 for s in scores if s < RED_MAX)
    green = sum(1 for s in scores if s >= GREEN_MIN)
    out = {
        "attempted": total,
        "scored": n,
        "failed": total - n,
        "avg": round(statistics.mean(scores), 1) if scores else None,
        "median": round(statistics.median(scores), 1) if scores else None,
        "red": red,
        "green": green,
        # shares are computed over the right denominator, and named for it
        "red_pct": round(100 * red / n) if n else None,
        "green_pct": round(100 * green / n) if n else None,
        "fail_pct": round(100 * (total - n) / total) if total else None,
        "best": max(scored, key=lambda r: r["perf_i"]) if scored else None,
        "worst": min(scored, key=lambda r: r["perf_i"]) if scored else None,
    }
    return out


def niche_table(rows: list[dict]) -> list[dict]:
    """Niche breakdown, fastest first, only niches that have scored sites."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["perf_i"] is not None:
            groups.setdefault(r["niche"], []).append(r)
    table = []
    for niche, niche_rows in groups.items():
        s = stats(niche_rows)
        table.append({
            "niche": niche,
            "label": NICHE_LABEL.get(niche, niche.title()),
            "n": s["scored"],
            "avg": s["avg"],
            "red_pct": s["red_pct"],
            "green_pct": s["green_pct"],
        })
    table.sort(key=lambda t: (t["avg"] is None, -(t["avg"] or 0)))
    return table


def commentary(s: dict, table: list[dict], unit: str = "sites") -> list[str]:
    """Rule 3: 2-3 lines derived from this group's own data, or nothing.

    Every line below is backed by a value computed above; no filler, no
    adjectives that the numbers do not support.
    """
    lines: list[str] = []
    if s["avg"] is not None:
        lines.append(
            f"Average mobile performance score across {s['scored']} measured "
            f"{unit}: {s['avg']}/100.")
    # A niche is only called fastest/slowest with enough sites behind it,
    # otherwise a two-site sample would be presented as a ranking.
    solid = [t for t in table if t["n"] >= MIN_NICHE_N]
    if len(solid) >= 2:
        fast, slow = solid[0], solid[-1]
        lines.append(
            f"Fastest industry measured here: {fast['label']} at "
            f"{fast['avg']}/100 (n={fast['n']}). Slowest: {slow['label']} at "
            f"{slow['avg']}/100 (n={slow['n']}).")
    if s["best"] and s["worst"] and s["best"]["url"] != s["worst"]["url"]:
        lines.append(
            f"Fastest site measured: {host_of(s['best'])} at "
            f"{s['best']['perf_i']}/100. Slowest: {host_of(s['worst'])} at "
            f"{s['worst']['perf_i']}/100.")
    if s["red_pct"] is not None:
        lines.append(
            f"{s['red_pct']}% of measured sites score below {RED_MAX}/100; "
            f"{s['green_pct']}% reach {GREEN_MIN} or better.")
    if s["failed"]:
        lines.append(
            f"{s['failed']} of {s['attempted']} tested URLs returned no usable "
            f"score ({s['fail_pct']}%) and are excluded from the averages.")
    return lines[:4]


def host_of(row: dict) -> str:
    return re.sub(r"^www\.", "", row["url"])


def distinct_urls(rows: list[dict]) -> list[dict]:
    """One row per website, newest measurement wins.

    A business with locations in several cities is measured once per city, so
    the ledger has one row per (url, city). Country and world totals must not
    count such a site twice, so they run over this list instead. City pages
    keep using every row, because each city legitimately has its own
    measurement of that site.
    """
    out: dict[str, dict] = {}
    for r in rows:
        prev = out.get(r["url"])
        if prev is None or (r["measured_at"], r["source_file"]) >= (
                prev["measured_at"], prev["source_file"]):
            out[r["url"]] = r
    return list(out.values())


def build_aggregate() -> dict:
    """The single JSON aggregate every page is rendered from."""
    countries = []
    for slug in ("canada", "united-states"):
        rows = load_country(slug)
        country = rows[0]["country"] if rows else COUNTRY_LABEL[slug]
        # totals count each website once ...
        total_rows = distinct_urls(rows)
        s = stats(total_rows)
        table = niche_table(total_rows)

        cities = []
        by_city: dict[str, list[dict]] = {}
        for r in rows:
            if r["city"] != "unknown":
                by_city.setdefault(r["city"], []).append(r)
        for city, city_rows in by_city.items():
            cs = stats(city_rows)
            cities.append({
                "city": city,
                "slug": slugify(city),
                "n": cs["scored"],
                "attempted": cs["attempted"],
                "avg": cs["avg"],
                "median": cs["median"],
                "red": cs["red"],
                "red_pct": cs["red_pct"],
                "green_pct": cs["green_pct"],
                "fail_pct": cs["fail_pct"],
                "rankable": cs["scored"] >= MIN_RANKABLE,
                "niches": niche_table(city_rows),
                "best": cs["best"],
                "worst": cs["worst"],
                "commentary": commentary(cs, niche_table(city_rows)),
            })
        cities.sort(key=lambda c: (not c["rankable"], -(c["avg"] or 0)))

        countries.append({
            "country": country,
            "slug": slug,
            "label": COUNTRY_LABEL[country],
            **s,
            "niches": table,
            "cities": cities,
            "ranked": [c for c in cities if c["rankable"]],
            "sampling": [c for c in cities if not c["rankable"]],
            # sites we could measure but could not place in a city: they are in
            # every country total, and the page has to say so out loud
            "unmapped": len({r["url"] for r in total_rows
                             if r["city"] == "unknown"}),
            "measurements": len(rows),
            "multi_city": sorted({r["url"] for r in rows
                                  if r.get("multi_city") == "yes"}),
            "commentary": commentary(s, table),
        })

    all_rows = []
    for slug in ("canada", "united-states"):
        all_rows += load_country(slug)
    glob_rows = distinct_urls(all_rows)
    glob_s = stats(glob_rows)
    glob_table = niche_table(glob_rows)
    ranked_cities = [c for cc in countries for c in cc["ranked"]]
    best_city = max(ranked_cities, key=lambda c: c["avg"]) if ranked_cities else None
    worst_city = min(ranked_cities, key=lambda c: c["avg"]) if ranked_cities else None

    return {
        "generated": date.today().isoformat(),
        "min_rankable": MIN_RANKABLE,
        "red_max": RED_MAX,
        "green_min": GREEN_MIN,
        "global": {
            **glob_s,
            "niches": glob_table,
            "countries": countries,
            "country_count": len(countries),
            "city_count": sum(len(c["cities"]) for c in countries),
            "ranked_city_count": len(ranked_cities),
            "best_city": best_city,
            "worst_city": worst_city,
            "multi_city_sites": sorted({u for c in countries
                                        for u in c["multi_city"]}),
            "commentary": commentary(glob_s, glob_table),
        },
    }


# ---------------------------------------------------------------------------
# tiny template engine: {{var}} and {{#list}}...{{/list}}
# ---------------------------------------------------------------------------
class Raw(str):
    """Marks a value as pre-built HTML (skips escaping)."""


def render(tpl: str, ctx: dict) -> str:
    def do_repeat(m: re.Match) -> str:
        name, body = m.group(1), m.group(2)
        out = []
        for item in ctx.get(name, []):
            sub = {**ctx, **item}
            out.append(_scalars(body, sub))
        return "".join(out)

    tpl = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", do_repeat, tpl, flags=re.S)
    return _scalars(tpl, ctx)


def _scalars(tpl: str, ctx: dict) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in ctx:
            return ""
        val = ctx[key]
        if val is None:
            return ""
        if isinstance(val, Raw):
            return str(val)
        if isinstance(val, (list, dict)):
            return json.dumps(val)
        return (str(val).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))
    return re.sub(r"\{\{(\w+)\}\}", sub, tpl)


def load_template(name: str) -> str:
    path = os.path.join(REPO, "templates", name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def content(name: str, default: str = "") -> str:
    path = os.path.join(REPO, "content", name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# row builders (tables live in Python; templates stay structure-only)
# ---------------------------------------------------------------------------
def e(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def city_rows(cities: list[dict]) -> Raw:
    out = []
    for i, c in enumerate(cities, 1):
        out.append(
            f'<tr><td class="num">{i}</td>'
            f'<td><a href="/cities/{c["slug"]}.html">{e(c["city"])}</a></td>'
            f'<td class="num">{c["n"]}</td>'
            f'<td class="num">{c["avg"]}</td>'
            f'<td class="num">{c["red_pct"]}%</td>'
            f'<td class="num">{c["green_pct"]}%</td></tr>')
    return Raw("\n".join(out))


def niche_rows(table: list[dict], city_link: bool = False) -> Raw:
    out = []
    for t in table:
        name = e(t["label"])
        if city_link:
            name = f'<a href="/cities/{t["city_slug"]}.html">{name}</a>'
        out.append(
            f'<tr><td>{name}</td><td class="num">{t["n"]}</td>'
            f'<td class="num">{t["avg"]}</td>'
            f'<td class="num">{t["red_pct"]}%</td>'
            f'<td class="num">{t["green_pct"]}%</td></tr>')
    return Raw("\n".join(out))


def sampling_rows(sampling: list[dict]) -> Raw:
    out = []
    for c in sampling:
        out.append(
            f'<tr><td>{e(c["city"])}</td><td class="num">{c["n"]}</td>'
            f'<td class="num">{c["attempted"]}</td></tr>')
    return Raw("\n".join(out))


def li_lines(lines: list[str]) -> Raw:
    return Raw("\n".join(f"<li>{line}</li>" for line in lines))


def multi_city_note(sites: list[str]) -> Raw:
    """Explain the one-to-many case instead of letting it look like a bug.

    A business with locations in two measured cities has one website, so it is
    measured once per city. It appears in both city tables with that city's
    own measurement, and is counted once in the country and world totals.
    """
    if not sites:
        return Raw("")
    shown = ", ".join(host_of({"url": u}) for u in sites[:6])
    more = f" and {len(sites) - 6} more" if len(sites) > 6 else ""
    return Raw(
        f"<li>{len(sites)} {'business has' if len(sites) == 1 else 'businesses have'} "
        f"locations in more than one measured city ({shown}{more}). One website "
        f"means one measurement, but each city keeps its own result and every "
        f"site is counted once in the totals above.</li>")


def country_cards(countries: list[dict]) -> Raw:
    """One card per country on the hub.

    The card component was designed for a single site's score ("8/100"), so
    the score slot holds an actual average score -- not the site count, which
    would read as a score out of 100.
    """
    out = []
    for c in countries:
        out.append(
            f'<div class="card">'
            f'<div class="card-score">{c["avg"]}'
            f'<span class="card-unit">/100 average</span></div>'
            f'<div class="card-lcp">{c["scored"]} sites measured · '
            f'{len(c["ranked"])} city pages · {c["red"]} below 50 '
            f'({c["red_pct"]}%)</div>'
            f'<div class="card-name"><a href="/countries/{c["slug"]}.html">'
            f'{e(c["label"])}</a></div></div>')
    return Raw("\n".join(out))


# ---------------------------------------------------------------------------
# the homepage ("Real sites. Real numbers.")
# ---------------------------------------------------------------------------
# The homepage makes three factual claims and shows four examples. All of them
# are now selected from the measured data instead of typed in, so they cannot
# go stale when a new wave lands.
CARD_PHRASE = {
    "dental": "A dental clinic",
    "hvac": "A heating and cooling company",
    "optometrist": "An optometrist",
    "physio": "A physiotherapy clinic",
    "realtor": "A real estate agency",
}


def example_cards(rows: list[dict], limit: int = 4) -> Raw:
    """Slowest real site per industry, preferring ones with a known city.

    Requires a recorded LCP so the card can state load time in seconds. Sites
    whose city is unknown are only used to fill a slot if nothing better
    exists -- a card must not invent a location.
    """
    usable = [r for r in rows
              if r["perf_i"] is not None and r["LCP_ms"].strip().isdigit()]
    worst_by_niche: dict[str, dict] = {}
    for r in sorted(usable, key=lambda r: (r["perf_i"], r["url"])):
        worst_by_niche.setdefault(r["niche"], r)

    picked, used = [], set()
    # pass 1: one per industry, city known
    for niche in ("hvac", "realtor", "optometrist", "dental", "physio"):
        r = worst_by_niche.get(niche)
        if r and r["url"] not in used and r["city"] != "unknown":
            picked.append(r)
            used.add(r["url"])
        if len(picked) == limit:
            break
    # pass 2: fill remaining slots with the next slowest measured sites
    if len(picked) < limit:
        for r in sorted(usable, key=lambda r: (r["perf_i"], r["url"])):
            if r["url"] in used:
                continue
            picked.append(r)
            used.add(r["url"])
            if len(picked) == limit:
                break

    out = []
    for r in picked:
        lcp = int(r["LCP_ms"]) / 1000
        phrase = CARD_PHRASE.get(r["niche"], "A local business")
        where = f' in {e(r["city"])}' if r["city"] != "unknown" else ""
        out.append(
            f'        <div class="card">\n'
            f'          <div class="card-score">{r["perf_i"]}'
            f'<span class="card-unit">/100</span></div>\n'
            f'          <div class="card-lcp">~{lcp:.1f} s to load a page on a phone</div>\n'
            f'          <div class="card-name">{phrase}{where}</div>\n'
            f'        </div>')
    return Raw("\n".join(out))


def gauge(score: int, lcp_ms: str) -> dict:
    """Needle position for a score on the 220x150 dial.

    Geometry already in the design: centre (110,115), radius 90, 0 at the left
    end and 100 at the right end, so angle = 180 - 1.8 * score. The green dot
    at 90 and the red zone ending at RED_MAX follow from the same numbers.
    """
    import math

    def point(s: float) -> str:
        ang = math.radians(180 - 1.8 * s)
        return f"{110 + 90 * math.cos(ang):.1f} {115 - 90 * math.sin(ang):.1f}"

    red_end = point(RED_MAX)
    nx, ny = point(score).split()
    lcp = f"{int(lcp_ms) / 1000:.1f}" if lcp_ms.strip().isdigit() else "?"
    return {
        "gauge_score": score,
        "gauge_lcp": lcp,
        "gauge_x": nx,
        "gauge_y": ny,
        "gauge_red_end": red_end,
        "gauge_aria": (f"Example: a measured site scores {score} out of 100, "
                       f"main content loads in about {lcp} seconds on a phone. "
                       f"Target zone is green, {GREEN_MIN} and above."),
    }


def render_home(agg: dict) -> str:
    """The conversion homepage, with its numbers generated from the data."""
    ca = next(c for c in agg["global"]["countries"] if c["slug"] == "canada")
    rows = load_country("canada")
    scored = [r for r in rows if r["perf_i"] is not None and r["LCP_ms"].strip().isdigit()]
    # worst measured Canadian site drives the hero dial: a real result beats
    # an illustration
    worst = min(scored, key=lambda r: (r["perf_i"], r["url"])) if scored else None

    ctx = base_ctx(
        agg,
        ca_sites=ca["scored"],
        ca_scored=ca["scored"],
        ca_attempted=ca["attempted"],
        ca_fail=ca["failed"],
        ca_avg=ca["avg"],
        ca_cities=len(ca["cities"]),
        cards=example_cards(rows),
    )
    ctx.update(gauge(worst["perf_i"], worst["LCP_ms"]) if worst else
               {"gauge_score": 0, "gauge_lcp": "?", "gauge_x": "110",
                "gauge_y": "115", "gauge_red_end": "110 25",
                "gauge_aria": "No measured example available."})
    return render(load_template("home.html"), ctx)


# ---------------------------------------------------------------------------
# page renderers
# ---------------------------------------------------------------------------
def base_ctx(agg: dict, **kw) -> dict:
    ctx = {
        "year": date.today().year,
        "generated": agg["generated"],
        "site": SITE,
        "red_max": agg["red_max"],
        "green_min": agg["green_min"],
        "min_rankable": agg["min_rankable"],
    }
    ctx.update(kw)
    return ctx


def page(template: str, ctx: dict) -> str:
    """Render a page body, then drop it into the shared shell."""
    body = render(load_template(template), ctx)
    return render(load_template("base.html"), {**ctx, "content": Raw(body)})


def render_index(agg: dict) -> str:
    g = agg["global"]
    ctx = base_ctx(
        agg,
        title="Website speed data by country and city — Site Speed",
        description=(f"Open data on website speed: {g['scored']} measured sites "
                     f"across {g['country_count']} countries and "
                     f"{g['ranked_city_count']} rankable cities, with raw CSV downloads."),
        canonical=f"{SITE}/speed-data/",
        heading="Website speed, measured and published.",
        sub=content("index.md", "Every number on this page is generated from the "
                                "raw audit data. Nothing is typed by hand."),
        attempted=g["attempted"], scored=g["scored"], avg=g["avg"],
        failed=g["failed"], fail_pct=g["fail_pct"],
        red_pct=g["red_pct"], green_pct=g["green_pct"],
        country_count=g["country_count"], city_count=g["city_count"],
        ranked_city_count=g["ranked_city_count"],
        global_notes=li_lines(g["commentary"]),
        country_cards=country_cards(g["countries"]),
        global_niches=niche_rows(g["niches"]),
        best_city=g["best_city"], worst_city=g["worst_city"],
        multi_city_note=multi_city_note(g["multi_city_sites"]),
    )
    return page("index.html", ctx)


def render_country(agg: dict, c: dict) -> str:
    ctx = base_ctx(
        agg,
        title=f"Website speed in {c['label']} — city ranking and industry data",
        description=(f"{c['scored']} measured websites in {c['label']}: average "
                     f"mobile score {c['avg']}/100, {c['red_pct']}% below 50. "
                     f"City ranking and raw data."),
        canonical=f"{SITE}/countries/{c['slug']}.html",
        heading=f"Website speed in {c['label']}",
        label=c["label"], slug=c["slug"],
        attempted=c["attempted"], scored=c["scored"], avg=c["avg"],
        median=c["median"], red=c["red"], red_pct=c["red_pct"],
        green_pct=c["green_pct"], failed=c["failed"], fail_pct=c["fail_pct"],
        city_count=len(c["cities"]), ranked_count=len(c["ranked"]),
        sampling_count=len(c["sampling"]),
        unmapped=c["unmapped"],
        min_rankable=agg["min_rankable"],
        country_notes=li_lines(c["commentary"]),
        city_rows=city_rows(c["ranked"]),
        sampling_rows=sampling_rows(c["sampling"]),
        niche_rows=niche_rows(c["niches"]),
        best_host=host_of(c["best"]) if c["best"] else "",
        best_perf=c["best"]["perf_i"] if c["best"] else "",
        worst_host=host_of(c["worst"]) if c["worst"] else "",
        worst_perf=c["worst"]["perf_i"] if c["worst"] else "",
    )
    return page("country.html", ctx)


def render_city(agg: dict, country: dict, c: dict) -> str:
    for t in c["niches"]:
        t["city_slug"] = c["slug"]
    ctx = base_ctx(
        agg,
        title=f"Website speed in {c['city']} — {c['n']} sites measured",
        description=(f"{c['n']} websites measured in {c['city']}, "
                     f"{country['label']}: average mobile speed score "
                     f"{c['avg']}/100. Industry breakdown and raw data."),
        canonical=f"{SITE}/cities/{c['slug']}.html",
        heading=f"Website speed in {c['city']}",
        city=c["city"], slug=c["slug"],
        country_label=country["label"], country_slug=country["slug"],
        n=c["n"], attempted=c["attempted"], avg=c["avg"], median=c["median"],
        red=c["red"], red_pct=c["red_pct"], green_pct=c["green_pct"],
        fail_pct=c["fail_pct"], city_notes=li_lines(c["commentary"]),
        niche_rows=niche_rows(c["niches"], city_link=False),
        best_host=host_of(c["best"]) if c["best"] else "",
        best_perf=c["best"]["perf_i"] if c["best"] else "",
        worst_host=host_of(c["worst"]) if c["worst"] else "",
        worst_perf=c["worst"]["perf_i"] if c["worst"] else "",
    )
    return page("city.html", ctx)


STATIC_URLS = ["/", "/audit", "/how-it-works", "/blog", "/contact",
               "/404", "/speed-data/",
               "/blog/canadian-website-speed-by-city",
               "/blog/canadian-website-speed-test",
               "/blog/canadian-website-speed-by-industry",
               "/blog/why-is-my-website-slow",
               "/blog/how-long-should-a-website-take-to-load",
               "/blog/website-speed-loses-customers"]


def render_sitemap(agg: dict) -> str:
    urls = list(STATIC_URLS)
    for c in agg["global"]["countries"]:
        urls.append(f"/countries/{c['slug']}.html")
        for city in c["ranked"]:
            urls.append(f"/cities/{city['slug']}.html")
    body = "\n".join(
        f"  <url><loc>{SITE}{u}</loc></url>" for u in dict.fromkeys(urls))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n")


# ---------------------------------------------------------------------------
# drift check: what the live pages claim vs what the data says
# ---------------------------------------------------------------------------
def drift(agg: dict) -> None:
    """Compare what site/index.html publishes with what the data says.

    The live homepage publishes CANADA numbers only, so Canada is the like
    for like comparison. The US numbers are new coverage, not a correction.
    """
    index = os.path.join(REPO, "site", "index.html")
    if not os.path.exists(index):
        return
    with open(index, encoding="utf-8") as f:
        html = f.read()

    def claimed(pattern: str) -> str | None:
        m = re.search(pattern, html)
        return m.group(1) if m else None

    g = agg["global"]
    ca = next((c for c in g["countries"] if c["slug"] == "canada"), None)
    us = next((c for c in g["countries"] if c["slug"] == "united-states"), None)
    if not ca:
        return

    checks = [
        ("canada sites audited",
         claimed(r'stat-num">(\d+)\+?<?[^<]*</span><span class="stat-label">sites audited'),
         ca["scored"]),
        ("canada average",
         claimed(r'stat-num">([\d.]+)/100'), ca["avg"]),
        ("canada cities",
         claimed(r'stat-num">(\d+)</span><span class="stat-label">cities'),
         len(ca["cities"])),
        ("canada cities with data", None, len(ca["cities"])),
    ]
    print("== drift: live site/index.html (Canada) vs regenerated data ==")
    for label, live, now in checks:
        if live is None:
            continue
        mark = "  " if str(live) == str(now) else "!!"
        print(f" {mark} {label:<22} live={live:<8} data={now}")
    print(f"    Canada: scored {ca['scored']}  avg {ca['avg']}  red {ca['red']} "
          f"({ca['red_pct']}% of scored)  fail {ca['failed']} ({ca['fail_pct']}%)")
    print(f"    Canada cities: {len(ca['cities'])} with data, "
          f"{len(ca['ranked'])} rankable (n>={agg['min_rankable']}), "
          f"{len(ca['sampling'])} still sampling, "
          f"{ca['attempted'] - sum(c['attempted'] for c in ca['cities'])} sites with no city")
    if us:
        print(f"    US (new coverage): scored {us['scored']}  avg {us['avg']}  "
              f"cities {len(us['cities'])}")


def update_readme(agg: dict) -> None:
    """Rewrite the census block in README.md from the data.

    The block used to be typed by hand and went stale on almost every wave,
    which is what produced the run of "fix: stale 650->788" commits. It is
    delimited by census:start / census:end markers and replaced wholesale.
    """
    path = os.path.join(REPO, "README.md")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start, end = "<!-- census:start", "<!-- census:end -->"
    if start not in text or end not in text:
        return
    g = agg["global"]
    ca = next((c for c in g["countries"] if c["slug"] == "canada"), None)
    us = next((c for c in g["countries"] if c["slug"] == "united-states"), None)
    best = g["best"]["perf_i"] if g.get("best") else "-"
    worst = g["worst"]["perf_i"] if g.get("worst") else "-"
    block = "\n".join([
        f"{start} - written by scripts/generate.py, do not edit by hand -->",
        f"- **{g['scored']}** business websites measured"
        + (f" (Canada {ca['scored']} · United States {us['scored']})"
           if ca and us else ""),
        f"- **{g['city_count']}** cities with data, "
        f"**{g['ranked_city_count']}** with a published city page",
        f"- **Average score: {g['avg']}/100** (sites with a usable measurement only)",
        f"- **{g['red']} sites scored under {RED_MAX}** — {g['red_pct']}%, "
        f"the red zone on Google's scale",
        f"- **{g['green']} sites reached green ({GREEN_MIN}+)** — "
        f"{g['green_pct']}% of sites",
        f"- **Best: {best} · Worst: {worst}**",
        f"- {g['attempted']} sites tested, {g['failed']} could not be measured "
        f"and are counted separately, never averaged in as zero",
        end,
    ])
    new = re.sub(re.escape(start) + r".*?" + re.escape(end), block, text, flags=re.S)
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        print("  updated README.md census block")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build",
                    help="output dir relative to repo (build = staging)")
    ap.add_argument("--check", action="store_true",
                    help="print aggregate + drift, write nothing")
    args = ap.parse_args()

    agg = build_aggregate()
    os.makedirs(os.path.join(REPO, "data"), exist_ok=True)
    with open(os.path.join(REPO, "data", "aggregate.json"), "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2, ensure_ascii=False)

    g = agg["global"]
    print("== global ==")
    print(f"  attempted {g['attempted']}  scored {g['scored']}  avg {g['avg']}"
          f"  red {g['red_pct']}%  green {g['green_pct']}%  fail {g['fail_pct']}%")
    print(f"  countries {g['country_count']}  cities {g['city_count']}"
          f"  rankable {g['ranked_city_count']}")
    for c in g["countries"]:
        print(f"  {c['label']:<14} scored {c['scored']:>4}  avg {c['avg']:>5}"
              f"  red {c['red_pct']:>3}%  cities {len(c['cities']):>3}"
              f"  rankable {len(c['ranked']):>3}  sampling {len(c['sampling']):>3}")
    for line in g["commentary"]:
        print(f"    - {line}")
    drift(agg)

    if args.check:
        return

    out_root = os.path.join(REPO, args.out)
    for sub in ("", "speed-data", "countries", "cities", "data"):
        os.makedirs(os.path.join(out_root, sub), exist_ok=True)

    written = []
    # The homepage keeps its hand-written pitch; only its numbers are generated
    # (templates/home.html). templates/index.html is the data hub and lives at
    # /speed-data/ so the conversion page at / is never replaced by a table.
    with open(os.path.join(out_root, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_home(agg))
    written.append("index.html")

    with open(os.path.join(out_root, "speed-data", "index.html"), "w",
              encoding="utf-8") as f:
        f.write(render_index(agg))
    written.append("speed-data/index.html")

    for c in g["countries"]:
        p = os.path.join(out_root, "countries", f"{c['slug']}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(render_country(agg, c))
        written.append(f"countries/{c['slug']}.html")
        for city in c["ranked"]:
            p = os.path.join(out_root, "cities", f"{city['slug']}.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(render_city(agg, c, city))
            written.append(f"cities/{city['slug']}.html")

    with open(os.path.join(out_root, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(render_sitemap(agg))
    written.append("sitemap.xml")

    # raw CSVs live next to the pages so the download links resolve
    for slug in ("canada", "united-states"):
        src = os.path.join(REPO, "data", slug, f"{slug}_all.csv")
        dst = os.path.join(out_root, "data", slug, f"{slug}_all.csv")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, encoding="utf-8") as a, open(dst, "w", encoding="utf-8") as b:
            b.write(a.read())
        written.append(f"data/{slug}/{slug}_all.csv")

    print()
    print(f"== wrote {len(written)} files to {args.out}/ ==")
    for w in written[:12]:
        print(f"  {w}")
    if len(written) > 12:
        print(f"  ... and {len(written) - 12} more")
    update_readme(agg)


if __name__ == "__main__":
    main()
