# speed.stephanedube.dev — Site Speed

Inbound lead-gen site for a one-person website-speed fix service.
Live at **https://speed.stephanedube.dev** (Cloudflare Pages).

Plain static HTML/CSS/JS — zero build step, zero image files, zero external
requests. One Cloudflare Pages Function powers the free audit tool; a second
powers the contact form.

## Pages
- `/` — home: pain story, real anonymized proof, how it works, referral block
- `/audit.html` — free audit form (URL + optional email) → live result via `/audit-api`
- `/how-it-works.html` — test → fix list → re-test
- `/blog.html` + 3 seed posts (`/blog/*.html`), each with sticky sidebar (CTA + related posts)
- `/contact.html` — form via `/contact-api` (Resend) + direct-email fallback

## Structure
```
speed/
├── index.html
├── audit.html
├── how-it-works.html
├── blog.html
├── contact.html
├── 404.html
├── sitemap.xml
├── robots.txt
├── favicon.svg
├── css/style.css
├── js/audit.js          # form logic; demo fallback if API not deployed
├── functions/api/audit.js    # Pages Function → Google PageSpeed Insights
├── functions/api/contact.js  # Pages Function → email via Resend
└── blog/*.html          # SEO seed posts
```

## Deploy (Cloudflare Pages)
1. Create a new Pages project in the Cloudflare dashboard → connect this repo
   (or upload the folder). Build settings: **none** (static, no build command).
2. Add the custom domain: **speed.stephanedube.dev** (Settings → Custom domains).
3. Add secrets. Cloudflare Pages does **not** read `.env` in production — set
   them in the dashboard or via Wrangler:
   - `PAGESPEED_KEY` — Google PageSpeed Insights API key (see `D:\Docs\Odin_Mod\.env`)
   - `RESEND_KEY` — Resend API key (free account at resend.com → API Keys)
   - Optional: `CONTACT_FROM` (default `onboarding@resend.dev` — switch to your
     own domain only after verifying a sending domain in Resend) and
     `CONTACT_TO` (default `audit@stephanedube.dev`)
   - CLI alternative (in this folder): `npx wrangler pages secret put <NAME>`
4. Functions deploy automatically: `POST /audit-api` and `POST /contact-api`.

Local testing (optional): Pages Functions read local secrets from `.dev.vars`,
not `.env`. Create `.dev.vars` with `PAGESPEED_KEY=AIza...` and
`RESEND_KEY=re_...` (no spaces around `=`), then `npx wrangler pages dev`.
Both `.env` and `.dev.vars` are gitignored — never commit secrets.

Test the APIs after deploy:
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
- Values are the real Google test (pagespeed.web.dev), never invented.
- Score bands: green 90+, orange 50-89, red <50. Goal = green, not 100.
- Proof numbers on the site are anonymized real audits from the outreach
  campaigns (no company names/emails shown).
- If `/audit-api` is not configured yet, the audit page shows a clearly-labeled
  demo result — never a fake "live" number.
- FR version of the site is a planned follow-up.