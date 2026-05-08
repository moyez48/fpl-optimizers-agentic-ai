/**
 * Proxies `/fpl-api/*` → FPL JSON API with browser-like headers (mirror of app/vite.config.js proxy).
 * Removes the brittle external rewrite-only path that omits UA/Referer.
 */

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

export const config = {
  matcher: ['/fpl-api', '/fpl-api/:path*'],
}

export default async function middleware(request) {
  const url = new URL(request.url)

  let subPath = url.pathname.slice('/fpl-api'.length) || '/'
  if (!subPath.startsWith('/')) subPath = `/${subPath}`

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method Not Allowed', { status: 405 })
  }

  const pathOnFpl = `/api${subPath}`
  const upstream = new URL(pathOnFpl + url.search, 'https://fantasy.premierleague.com').href

  const upstreamResp = await fetch(upstream, {
    method: request.method,
    headers: {
      'User-Agent': UA,
      Accept: 'application/json, text/plain, */*',
      'Accept-Language': 'en-GB,en;q=0.9',
      Referer: 'https://fantasy.premierleague.com/',
    },
  })

  const out = new Headers()
  const ct = upstreamResp.headers.get('content-type')
  if (ct) out.set('content-type', ct)
  const cache = upstreamResp.headers.get('cache-control')
  if (cache) out.set('cache-control', cache)

  return new Response(upstreamResp.body, {
    status: upstreamResp.status,
    headers: out,
  })
}
