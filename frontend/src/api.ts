import type { Health, Message, Result, Evidence } from './types'

export const API = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'

async function parse<T>(r: Response): Promise<T> {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${r.status})`)
  return data as T
}

export const getHealth = () => fetch(`${API}/health`).then(r => parse<Health>(r))

/** Single entry point: sends file and/or notes (multimodal) to /upload, or plain text to /analyze. */
export function analyze(text: string, features: Record<string, number>, file: File | null): Promise<Result> {
  if (!file) {
    return fetch(`${API}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, risk_features: features }) }).then(r => parse<Result>(r))
  }
  const body = new FormData()
  body.append('file', file); body.append('notes', text); body.append('risk_features', JSON.stringify(features))
  return fetch(`${API}/upload`, { method: 'POST', body }).then(r => parse<Result>(r))
}

export const chat = (message: string, context: string, history: Message[]) =>
  fetch(`${API}/chat`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context, history: history.map(({ role, content }) => ({ role, content })).slice(-8) }),
  }).then(r => parse<{ reply: string; evidence: Evidence[] }>(r))
