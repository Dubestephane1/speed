// Worker entry: serves static assets AND the API routes.
// - POST /audit-api   -> Google PageSpeed Insights (functions/api/audit.js)
// - POST /contact-api -> email via Resend                (functions/api/contact.js)
// - everything else   -> static assets (env.ASSETS)

import { onRequestPost as auditApi } from '../functions/api/audit.js';
import { onRequestPost as contactApi } from '../functions/api/contact.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/audit-api') {
      return auditApi({ request, env, ctx });
    }
    if (request.method === 'POST' && url.pathname === '/contact-api') {
      return contactApi({ request, env, ctx });
    }

    // Static pages (index.html, audit.html, blog, css, js, ...)
    return env.ASSETS.fetch(request);
  },
};