/**
 * Pitchcraft dashboard API base — uses VITE_API_BASE when set (HF / prod).
 * Empty base keeps relative URLs so Vite dev proxy forwards `/api/*` → FastAPI.
 *
 * Backend squad route (backend/main.py): GET /api/squad?entry=<fpl_id>
 * VITE_API_BASE must be the Space origin only (no trailing slash, no /api suffix).
 */
function normalizeApiBase(raw) {
  if (typeof raw !== 'string') return ''
  let base = raw.trim().replace(/\/+$/, '')
  if (base.endsWith('/api')) base = base.slice(0, -4)
  return base
}

export function pitchcraftApiUrl(pathAndQuery) {
  const base = normalizeApiBase(import.meta.env.VITE_API_BASE)
  const piece = pathAndQuery.startsWith('/') ? pathAndQuery : `/${pathAndQuery}`
  return base ? `${base}${piece}` : piece
}

/** Exact backend route for Load Team — @app.get("/api/squad") with query param entry. */
export function squadFetchUrl(entryId, gw = null) {
  const params = new URLSearchParams()
  params.set('entry', String(entryId).trim())
  if (gw != null) params.set('gw', String(gw))
  return pitchcraftApiUrl(`/api/squad?${params.toString()}`)
}
