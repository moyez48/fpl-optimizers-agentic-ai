/**
 * Pitchcraft dashboard API base — uses VITE_API_BASE when set (HF / prod).
 * Empty base keeps relative URLs so Vite dev proxy forwards `/api/*` → FastAPI.
 */
export function pitchcraftApiUrl(pathAndQuery) {
  const raw = import.meta.env.VITE_API_BASE
  const base = typeof raw === 'string' ? raw.trim().replace(/\/+$/, '') : ''
  const piece = pathAndQuery.startsWith('/') ? pathAndQuery : `/${pathAndQuery}`
  return base ? `${base}${piece}` : piece
}
