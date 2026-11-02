import { accessToken } from './oidc'
import type { AuthConfig, CaseDetail, CaseSummary, Feedback, Health, Me, Message, ModelCard, Result, Evidence } from './types'

export const API = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'
const V1 = `${API}/v1`
const KEY_STORAGE = 'clarity.apiKey'

/** The API key lives in sessionStorage only: it is never bundled into the build and is cleared when the tab closes. */
export const apiKey = {
  get: () => { try { return sessionStorage.getItem(KEY_STORAGE) ?? '' } catch { return '' } },
  set: (v: string) => { try { if (v) { sessionStorage.setItem(KEY_STORAGE, v) } else { sessionStorage.removeItem(KEY_STORAGE) } } catch { /* storage blocked */ } },
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly requestId?: string) { super(message) }
}

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {}
  if (json) h['Content-Type'] = 'application/json'
  const credential = accessToken() ?? apiKey.get()   // SSO session first, then a configured API key
  if (credential) h.Authorization = `Bearer ${credential}`
  return h
}

async function parse<T>(r: Response): Promise<T> {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const rid = data.request_id ?? r.headers.get('X-Request-ID') ?? undefined
    const detail = typeof data.detail === 'string' ? data.detail
      : Array.isArray(data.detail) ? data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ')
      : `Request failed (${r.status})`
    const hint = r.status === 401 ? ' Sign in, or add an API key in Settings.' : r.status === 429 ? ` Try again in ${r.headers.get('Retry-After') ?? 'a few'} seconds.` : ''
    throw new ApiError(detail + hint, r.status, rid)
  }
  return data as T
}

/** Short timeout so a sleeping free-tier server is detected quickly and the UI can show its wake-up state. */
export const getHealth = (timeoutMs = 8000) => fetch(`${V1}/health`, { signal: AbortSignal.timeout(timeoutMs) }).then(r => parse<Health>(r))

/** Single entry point: sends file and/or notes (multimodal) to /upload, or plain text to /analyze. */
export function analyze(text: string, features: Record<string, number>, file: File | null): Promise<Result> {
  if (!file) {
    return fetch(`${V1}/analyze`, { method: 'POST', headers: headers(), body: JSON.stringify({ text, risk_features: features }) }).then(r => parse<Result>(r))
  }
  const body = new FormData()
  body.append('file', file); body.append('notes', text); body.append('risk_features', JSON.stringify(features))
  return fetch(`${V1}/upload`, { method: 'POST', headers: headers(false), body }).then(r => parse<Result>(r))
}

export const chat = (message: string, context: string, history: Message[]) =>
  fetch(`${V1}/chat`, {
    method: 'POST', headers: headers(),
    body: JSON.stringify({ message, context, history: history.map(({ role, content }) => ({ role, content })).slice(-8) }),
  }).then(r => parse<{ reply: string; evidence: Evidence[] }>(r))

export const sendFeedback = (f: Feedback) =>
  fetch(`${V1}/feedback`, { method: 'POST', headers: headers(), body: JSON.stringify(f) }).then(r => parse<{ status: string; audit_seq: number | null }>(r))

export const fhirBundle = (result: Result) =>
  fetch(`${V1}/fhir/bundle`, { method: 'POST', headers: headers(), body: JSON.stringify(result) }).then(r => parse<Record<string, unknown>>(r))

export const getAuthConfig = () => fetch(`${V1}/auth/config`).then(r => parse<AuthConfig>(r))
export const getModels = () => fetch(`${V1}/models`).then(r => parse<Record<string, ModelCard>>(r))
export const getMe = () => fetch(`${V1}/me`, { headers: headers(false) }).then(r => parse<Me>(r))
export const listCases = () => fetch(`${V1}/cases`, { headers: headers(false) }).then(r => parse<{ enabled: boolean; retention_days?: number; cases: CaseSummary[] }>(r))
export const getCase = (id: string) => fetch(`${V1}/cases/${encodeURIComponent(id)}`, { headers: headers(false) }).then(r => parse<CaseDetail>(r))
export const deleteCase = (id: string) =>
  fetch(`${V1}/cases/${encodeURIComponent(id)}`, { method: 'DELETE', headers: headers(false) }).then(r => { if (!r.ok) return parse(r); return undefined })
