// Cloudflare Pages Function: POST /audit-api
// Calls Google PageSpeed Insights (mobile, performance) with the PAGESPEED_KEY secret
// and returns a small normalized payload for the audit page.
//
// Deploy: place in functions/api/audit.js of a Cloudflare Pages project.
// Secret: set PAGESPEED_KEY in the Pages project settings (Environment variables).

export async function onRequestPost(context) {
  const key = context.env.PAGESPEED_KEY;
  if (!key) {
    return json({ error: "server_not_configured" }, 500);
  }

  let url;
  try {
    const body = await context.request.json();
    url = new URL(body.url);
    if (!/^https?:$/.test(url.protocol)) throw new Error("bad protocol");
  } catch (e) {
    return json({ error: "invalid_url" }, 400);
  }

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

  return json({
    score: score,
    lcp_sec: lcpSec === null ? null : lcpSec.toFixed(1),
    issues: issues
  }, 200);
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