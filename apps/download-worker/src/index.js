// The only way to the installer. The site's Download button runs a Cloudflare Turnstile check and sends its token
// here; this Worker verifies the token with Cloudflare (single-use, valid 5 minutes, issued on our own site) and
// only then streams the file from the private R2 bucket. No public link to the file exists, so bots that skip the
// site get nothing.
const KEY = 'YT-Clipper-Setup.exe'
const SITE = 'https://ytclipper.xyz'

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    if (url.pathname !== '/download') return page(404, 'Nothing here.', 'Download YT Clipper from the website.')
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response(null, { status: 405 })

    const token = url.searchParams.get('t')
    if (!token) return page(400, 'Start the download from the website.', 'A quick check there keeps bots away from the file.')

    const form = new FormData()
    form.append('secret', env.TURNSTILE_SECRET)
    form.append('response', token)
    const ip = request.headers.get('CF-Connecting-IP')
    if (ip) form.append('remoteip', ip)
    let check
    try {
      check = await (await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body: form })).json()
    } catch {
      return page(502, 'The check could not be confirmed.', 'Go back and press Download again in a moment.')
    }
    const hosts = (env.ALLOWED_HOSTS || 'ytclipper.xyz,www.ytclipper.xyz').split(',')
    if (!check.success || !hosts.includes(check.hostname)) {
      return page(403, 'That check has expired.', 'Each check works once, for five minutes. Go back and press Download again.')
    }

    const object = await env.RELEASES.get(KEY)
    if (!object) return page(503, 'The installer is being updated.', 'Try again in a few minutes.')
    return new Response(request.method === 'HEAD' ? null : object.body, {
      headers: {
        'content-type': 'application/vnd.microsoft.portable-executable',
        'content-length': String(object.size),
        'content-disposition': `attachment; filename="${KEY}"`,
        'cache-control': 'no-store',
        'x-content-type-options': 'nosniff',
      },
    })
  },
}

/** A small branded page for every refusal, with the way back. Text only, nothing from the request is echoed. */
function page(status, title, body) {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | YT Clipper</title><meta name="robots" content="noindex">
<style>body{margin:0;min-height:100dvh;display:grid;place-items:center;background:#f2f3f5;color:#111214;font:16px/1.6 system-ui,sans-serif;padding:24px}
main{max-width:440px;background:#fff;border-radius:24px;padding:36px;box-shadow:0 30px 70px -36px rgb(27 42 16/.35)}
h1{margin:0 0 8px;font-size:24px;letter-spacing:-.02em}p{margin:0 0 24px;color:#474a52}
a{display:inline-block;background:#111214;color:#f2f3f5;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:999px}
@media (prefers-color-scheme:dark){body{background:#0d0e10;color:#f2f3f5}main{background:#16171a}p{color:#b6b9c0}a{background:#f2f3f5;color:#111214}}</style>
</head><body><main><h1>${title}</h1><p>${body}</p><a href="${SITE}">Back to ytclipper.xyz</a></main></body></html>`
  return new Response(html, { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } })
}
