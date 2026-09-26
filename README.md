# speed.stephanedube.dev — Site Speed

Inbound lead-gen site for a one-person website-speed fix service.
Live at **https://speed.stephanedube.dev** — **Cloudflare Workers + static assets**, Git-connected auto-deploy.

Plain static HTML/CSS/JS — zero build step, zero frameworks, zero image requests (visuals are pure CSS + one SVG favicon). One Worker handles the two APIs.

## What it does
- **Free mobile speed audit** — enter any URL, get a real Google PageSpeed Insights result (score, load time, fix hints) via `POST /audit-api`
- **Contact form** — email via Resend via `POST /contact-api` (sending domain `stephanedube.dev` verified in Resend)
- **SEO/social** — canonical, OG/Twitter cards, JSON-LD, branded `og-image.png`, `robots.txt`, `sitemap.xml` (extensionless URLs)
- **Proof** — homepage shows real anonymized audits across Canada: 788+ sites tested, average 54.9/100, 50 cities (BC/QC/ON/MB examples)

## Current verified stats (audit campaign, mobile / slow 4G)
<!-- census:start - written by scripts/generate.py, do not edit by hand -->
- **1731** business websites measured (Canada 931 · United States 800)
- **80** cities with data, **37** with a published city page
- **Average score: 57.5/100** (sites with a usable measurement only)
- **613 sites scored under 50** — 35%, the red zone on Google's scale
- **110 sites reached green (90+)** — 6% of sites
- **Best: 100 · Worst: 4**
- 1773 sites tested, 42 could not be measured and are counted separately, never averaged in as zero
<!-- census:end -->

> Every number is the real Google PageSpeed mobile test (homepage, simulated phone, slow 4G) — never invented. Raw CSVs are published next to the pages, and this block is generated: re-run `scripts/generate.py` after a new wave rather than typing figures here.

## Pages
- `/` — home: pain story, Canada-wide proof + stats, how it works, referral block
- `/speed-data/` — data hub: all countries, industries and city pages, plus raw CSV downloads
- `/countries/*.html` · `/cities/*.html` — generated atlas pages (no hand-written numbers)
- `/audit` — free audit form (URL + optional email) → live result via `/audit-api`
- `/how-it-works` — test → fix list → re-test
- `/blog` + 4 posts (`/blog/*`), each with sidebar (CTA + related posts). Flagship: "I tested 788 Canadian websites"
- `/contact` — form via `/contact-api` (Resend) + direct-email fallback
- URLs are extensionless (Cloudflare pretty URLs): `/audit`, `/blog/why-is-my-website-slow`, … (`/audit.html` variants also respond via 307 → 200)

## Sampling design
- **US city waves: exactly 20 sites per industry, 100 per city. No more, no less.** Checked by `scripts/check_wave_shape.py`, which exits non-zero on any deviation. This rule exists because the Chicago wave once published 99 sites after a URL measured in two city waves was deduped away from one of them, and nothing complained.
- **Canada is a census, not a sample.** City counts are deliberately uneven (Toronto 90, Montreal 26): every site the outreach waves happened to measure is included, and 79 measured sites still have no known city (listed in `data/mapping_gaps.csv`).
- A city earns a published page at 10+ scored sites. Below that it is listed as "sampling in progress" and never ranked.
- A business with locations in two measured cities has one website, so it is measured once per city: it appears in both city tables with that city's own result and is counted once in the country and world totals.

## Regenerating after a new wave
```
python scripts/sync_data.py        # fold wave CSVs into data/<country>/*_all.csv + mapping gaps
python scripts/backfill_cities.py  # read footer addresses for sites no record knows (network reads only)
python scripts/generate.py         # build/ staging — review here
python scripts/check_links.py      # every internal link resolves
python scripts/check_wave_shape.py # US waves still 20-per-niche / 100-per-city
python scripts/generate.py --out site   # promote to the deployed tree
```
`scripts/generate.py --check` prints the aggregate and a drift report (what `site/index.html` claims vs what the data says) and writes nothing. Nothing in `site/` is hand-edited from here on.

## Structure
```
speed/
├── wrangler.toml     # name="speed", main="src/index.js", [assets] directory="site", not_found_handling="404-page"
├── src/index.js      # single Worker: routes /audit-api + /contact-api, serves assets, clean 404 fallback
├── site/             # static assets served at /
│   ├── index.html · audit.html · how-it-works.html · blog.html · contact.html · 404.html
│   ├── blog/*.html   # SEO posts (5-6 min reads, Article JSON-LD)
│   ├── css/style.css
│   ├── js/audit.js   # form logic; clearly-labeled demo fallback if API is unreachable
│   ├── favicon.svg · og-image.png
│   └── robots.txt · sitemap.xml
└── README.md
```

## Deploy (Cloudflare Workers)
1. Worker `speed` (account `dubestephane@protonmail.com`) is Git-connected to this repo, branch `main`.
2. Push to `main` → Cloudflare auto-deploys (~1 min). No build config needed — `wrangler.toml` drives it.
3. Secrets are set once via Wrangler CLI (never committed — `.env`/`.dev.vars` are gitignored):
   - `PAGESPEED_KEY` — Google PageSpeed Insights API key (source: `D:\Docs\Odin_Mod\.env`)
   - `RESEND_KEY` — Resend API key (free account; sending domain `stephanedube.dev` verified, DNS CNAMEs `rsend`/`send` in Cloudflare)
   - `npx wrangler secret put PAGESPEED_KEY` / `npx wrangler secret put RESEND_KEY`
4. Custom domain: `speed.stephanedube.dev` A/AAAA records point to the worker in Cloudflare DNS.

Manual deploy / local dev:
- `npx wrangler dev` from this folder (reads local `.dev.vars` — create it with the same keys, no spaces around `=`)
- `npx wrangler deploy` pushes manually (Git integration usually supersedes this)

## Test after deploy
```
curl -X POST https://speed.stephanedube.dev/audit-api ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://example.com\"}"
```
```
curl -X POST https://speed.stephanedube.dev/contact-api ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Jane\",\"email\":\"jane@example.com\",\"message\":\"Hello — need help with a slow site.\"}"
```

## Honest notes
- Every score on the site is the real Google test (pagespeed.web.dev) — never invented.
- Score bands: green 90+, orange 50-89, red <50. Goal is green, not 100.
- Proof examples are anonymized real audits from the outreach campaigns (no company names/emails shown).
- Cloudflare RUM (Web Analytics beacon) is enabled on the custom domain — free analytics; it costs a couple of points on mobile PageSpeed (99, not 100).
- If `/audit-api` is unreachable, the audit page shows a clearly-labeled demo result — never a fake "live" number.
- FR version of the site is a planned follow-up.