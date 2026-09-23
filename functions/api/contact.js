// POST /contact-api — contact form -> email via Resend.
// Env vars (Cloudflare Pages -> Settings -> Environment variables, all Encrypted):
//   RESEND_KEY    required — Resend API key (free tier: 100 emails/day)
//   CONTACT_FROM  optional — sender. Default sends from the verified domain
//                            hello@stephanedube.dev (required once verified).
//   CONTACT_TO    optional — delivery inbox. Default audit@stephanedube.dev

const DEFAULT_FROM = 'Site Speed <hello@stephanedube.dev>';
const DEFAULT_TO = 'audit@stephanedube.dev';

export async function onRequestPost(context) {
  const { request, env } = context;

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: 'Invalid JSON body.' }, 400);
  }

  const name = String(body.name || '').trim();
  const email = String(body.email || '').trim();
  const url = String(body.url || '').trim();
  const message = String(body.message || '').trim();
  const honey = String(body._honey || '').trim();

  // Honeypot: bots fill the hidden field. Answer success, drop silently.
  if (honey) return json({ ok: true }, 200);

  if (!name || name.length < 2) return json({ ok: false, error: 'Please enter your name.' }, 400);
  if (!isEmail(email)) return json({ ok: false, error: 'Please enter a valid email address.' }, 400);
  if (!message || message.length < 10) return json({ ok: false, error: 'Tell me a little more (10+ characters).' }, 400);

  const RESEND_KEY = env.RESEND_KEY;
  if (!RESEND_KEY) {
    return json({ ok: false, error: 'Contact form is not configured yet (missing RESEND_KEY).' }, 500);
  }

  const lines = [
    `Name: ${name}`,
    `Email: ${email}`,
    url ? `Website: ${url}` : 'Website: —',
    '',
    message,
  ];

  let res;
  try {
    res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${RESEND_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: env.CONTACT_FROM || DEFAULT_FROM,
        to: [env.CONTACT_TO || DEFAULT_TO],
        reply_to: email,
        subject: `Contact form: ${truncate(name, 40)}`,
        text: lines.join('\n'),
      }),
    });
  } catch {
    return json({ ok: false, error: 'Could not reach the email service.' }, 502);
  }

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    console.error('Resend error', res.status, detail);
    return json({ ok: false, error: 'The email service rejected the message.' }, 502);
  }

  return json({ ok: true }, 200);
}

function isEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v);
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + '\u2026' : s;
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}