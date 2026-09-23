// Cloudflare Pages Function: POST /audit-api
// Calls Google PageSpeed Insights (mobile, performance) with the PAGESPEED_KEY secret
// and returns a small normalized payload for the audit page.
//
// Lead capture: when the visitor provides an email, the lead is forwarded to the
// audit inbox (audit@stephanedube.dev) via Resend so the fix-list report can be sent.
// The email send never blocks or fails the audit response.
//
// Deploy: place in functions/api/audit.js of a Cloudflare Pages project.
// Secrets (set once, never committed):
//   PAGESPEED_KEY  required — Google PageSpeed Insights API key
//   RESEND_KEY     required for lead emails — Resend API key (same as contact)
//   CONTACT_FROM   optional — sender. Default: hello@stephanedube.dev
//   CONTACT_TO     optional — delivery inbox. Default: audit@stephanedube.dev

const DEFAULT_FROM = 'Site Speed <hello@stephanedube.dev>';
const DEFAULT_TO = 'audit@stephanedube.dev';

export async function onRequestPost(context) {
  const key = context.env.PAGESPEED_KEY;
  if (!key) {
    return json({ error: "server_not_configured" }, 500);
  }

  let url;
  let leadEmail = "";
  let honey = "";
  try {
    const body = await context.request.json();
    url = new URL(body.url);
    if (!/^https?:$/.test(url.protocol)) throw new Error("bad protocol");
    leadEmail = String(body.email || "").trim();
    honey = String(body._honey || "").trim();
  } catch (e) {
    return json({ error: "invalid_url" }, 400);
  }

  // Honeypot: bots fill the hidden field. Answer success, drop silently,
  // and never spend a PageSpeed quota on them.
  if (honey) return json({ ok: true }, 200);

  const psUrl = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" +
    new URLSearchParams({
      url: url.toString(),
      strategy: "mobile",
      category: "performance",
      key: key
    });

  let ps;
  try {
    const r = await fetch(psUrl, { headers: { "Accept": "application/json" } });
    if (!r.ok) {
      return json({ error: "pagespeed_http_" + r.status }, 502);
    }
    ps = await r.json();
  } catch (e) {
    return json({ error: "pagespeed_unreachable" }, 502);
  }

  const lr = ps.lighthouseResult;
  if (!lr) {
    return json({ error: "pagespeed_no_result" }, 502);
  }

  const perf = lr.categories.performance;
  const score = perf && typeof perf.score === "number"
    ? Math.round(perf.score * 100)
    : null;

  const audits = lr.audits || {};
  const lcp = audits["largest-contentful-paint"];
  const lcpSec = lcp && lcp.displayValue
    ? parseFloat(String(lcp.displayValue).replace(/[^\d.]/g, ""))
    : null;

  // Worst 3 performance audits that are failing or need improvement
  const perfRefs = (perf && perf.auditRefs) || [];
  const issues = perfRefs
    .map(function (ref) {
      const a = audits[ref.id];
      return a ? { id: ref.id, title: a.title, score: a.score } : null;
    })
    .filter(function (a) {
      return a && a.score !== null && typeof a.score === "number" && a.score < 0.9;
    })
    .sort(function (a, b) { return a.score - b.score; })
    .slice(0, 3)
    .map(function (a) { return { id: a.id, title: a.title }; });

  // Lead capture: valid email -> fire-and-forget a Resend notification so the
  // fix-list report can be sent. Never blocks or fails the audit response.
  if (leadEmail && isEmail(leadEmail) && context.env.RESEND_KEY) {
    try {
      const lead = {
        email: leadEmail,
        url: url.toString(),
        score: score,
        lcp_sec: lcpSec === null ? null : lcpSec.toFixed(1),
        issues: issues
      };
      context.ctx.waitUntil(notifyLead(context.env, lead));
    } catch (e) {
      console.error("audit lead email queue failed", e);
    }
  }

  return json({
    score: score,
    lcp_sec: lcpSec === null ? null : lcpSec.toFixed(1),
    issues: issues
  }, 200);
}

// Send the lead to the audit inbox via Resend. Errors are logged, never thrown
// into the audit response.
async function notifyLead(env, lead) {
  try {
    const lines = [
      "Audit lead — visitor asked for the full fix list.",
      "",
      `Email: ${lead.email}`,
      `Website: ${lead.url}`,
      `Score: ${lead.score}/100`,
      lead.lcp_sec !== null ? `Main content LCP: ${lead.lcp_sec}s` : null,
      lead.issues && lead.issues.length
        ? "Top problems:\n- " + lead.issues.map(function (i) { return i.title; }).join("\n- ")
        : null,
      "",
      "Send them the full fix list from PageSpeed."
    ].filter(function (l) { return l !== null; }).join("\n");

    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.RESEND_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        from: env.CONTACT_FROM || DEFAULT_FROM,
        to: [env.CONTACT_TO || DEFAULT_TO],
        reply_to: lead.email,
        subject: `Audit lead: ${truncate(lead.url, 40)} — ${lead.score}/100`,
        text: lines
      })
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      console.error("Audit lead Resend error", res.status, detail);
    }
  } catch (e) {
    console.error("Audit lead email failed", e);
  }
}

function isEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v);
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "\u2026" : s;
}

function json(payload, status) {
  return new Response(JSON.stringify(payload), {
    status: status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*"
    }
  });
}