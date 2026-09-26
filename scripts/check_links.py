#!/usr/bin/env python3
"""Check that every internal link in the generated pages resolves.

Generated pages live in the output dir; the hand-written pages (audit, blog,
contact...) live in site/ and are referenced by extensionless URL. This script
therefore resolves each link against BOTH trees and reports anything that
matches neither, so a typo in a template cannot ship as a 404.

USAGE
    python scripts/check_links.py                # checks build/ against site/
    python scripts/check_links.py --out site     # checks a promoted site/
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# URLs that exist as hand-written pages (extensionless) or are static assets.
KNOWN = {
    "/", "/audit", "/how-it-works", "/blog", "/contact", "/404",
    "/speed-data/", "/css/style.css", "/favicon.svg", "/og-image.png",
    "/robots.txt", "/sitemap.xml",
}
KNOWN |= {"/blog/" + slug for slug in (
    "canadian-website-speed-by-city", "canadian-website-speed-test",
    "canadian-website-speed-by-industry", "why-is-my-website-slow",
    "how-long-should-a-website-take-to-load", "website-speed-loses-customers")}

HREF = re.compile(r'(?:href|src)="(/[^"]*)"')


def urls_in_tree(root: str) -> set[str]:
    found: set[str] = set()
    for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        rel = "/" + os.path.relpath(path, root).replace(os.sep, "/")
        if rel.endswith("/index.html"):
            rel = rel[: -len("index.html")]
        found.add(rel)
        found.add(rel.rstrip("/") or "/")
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build", help="generated output dir")
    args = ap.parse_args()

    out_root = os.path.join(REPO, args.out)
    site_root = os.path.join(REPO, "site")
    if not os.path.isdir(out_root):
        sys.exit(f"missing {out_root}")

    resolvable = urls_in_tree(out_root) | urls_in_tree(site_root) | KNOWN
    pages = glob.glob(os.path.join(out_root, "**", "*.html"), recursive=True)

    broken: dict[str, list[str]] = {}
    total = 0
    for page in pages:
        with open(page, encoding="utf-8") as f:
            for href in HREF.findall(f.read()):
                total += 1
                target = href.split("#")[0].split("?")[0]
                if not target or target in resolvable:
                    continue
                broken.setdefault(target, []).append(
                    os.path.relpath(page, REPO).replace(os.sep, "/"))

    print(f"pages checked      : {len(pages)}")
    print(f"internal links     : {total}")
    print(f"resolvable targets : {len(resolvable)}")
    print(f"broken links       : {len(broken)}")
    for target in sorted(broken):
        where = ", ".join(broken[target][:3])
        print(f"  {target}  <- {where}")
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
