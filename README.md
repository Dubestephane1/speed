# speed.stephanedube.dev — Site Speed

Inbound lead-gen site for a one-person website-speed fix service.
Live at **https://speed.stephanedube.dev** — **Cloudflare Workers + static assets**, Git-connected auto-deploy.

Plain static HTML/CSS/JS — zero build step, zero frameworks, zero image requests (visuals are pure CSS + one SVG favicon). One Worker handles the two APIs.

## What it does
- **Free mobile speed audit** — enter any URL, get a real Google PageSpeed Insights result (score, load time, fix hints) via `POST /audit-api`
- **Contact form** — email via Resend via `POST /contact-api` (sending domain `stephanedube.dev` verified in Resend)
- **SEO/social** — canonical, OG/Twitter cards, JSON-LD, branded `og-image.png`, `robots.txt`, `sitemap.xml` (extensionless URLs)
- **Proof** — homepage shows real anonymized audits across Canada: 368+ sites tested, average 58/100, 13 cities (QC/MB/ON/BC examples)

## Pages
- `/` — home: pain story, Canada-wide proof + stats, how it works, referral block
- `/audit` — free audit form (URL + optional email) → live result via `/audit-api`
- `/how-it-works` — test → fix list → re-test
- `/blog` + 4 posts (`/blog/*`), each with sidebar (CTA + related posts). Flagship: "I tested 368 Canadian websites"
- `/contact` — form via `/contact-api` (Resend) + direct-email fallback
- URLs are extensionless (Cloudflare pretty URLs): `/audit`, `/blog/why-is-my-website-slow`, … (`/audit.html` variants also respond via 307 → 200)

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