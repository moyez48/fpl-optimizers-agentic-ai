/**
 * Production FastAPI origin for Stats / Manager / Transfers.
 * - Local dev (default): empty → same-origin `/api/*` via Vite proxy.
 * - Vercel: set `VITE_API_BASE` to your API host, no trailing slash, e.g. https://your-api.up.railway.app
 */

function stripTrailingSlash(s) {
  return s.replace(/\/+$/, '')
}

function normalizeApiBase(raw) {
  const s = typeof raw === 'string' ? raw.trim() : ''
  if (!s) return ''
  let base = stripTrailingSlash(s)
  if (base.endsWith('/api')) base = base.slice(0, -4)
  return base
}

export function backendApiOrigin() {
  return normalizeApiBase(import.meta.env.VITE_API_BASE)
}

/** Path must start with / (e.g. `/api/stats`). Returns absolute URL in prod when VITE_API_BASE is set. */
export function backendApiUrl(path) {
  const p = typeof path === 'string' ? path.trim() : ''
  const prefix = backendApiOrigin()
  const piece = prefix ? `${stripTrailingSlash(prefix)}${p.startsWith('/') ? p : `/${p}`}` : path
  return piece
}
