/** OIDC authorization-code + PKCE sign-in for a public SPA client (no client secret in the browser).
 *  Tokens are kept in sessionStorage (cleared with the tab), never localStorage. */
export type OidcConfig = { issuer: string; client_id: string; scope: string }
type Discovery = { authorization_endpoint: string; token_endpoint: string; end_session_endpoint?: string }

const TOKEN = 'clarity.oidc.token'
const PENDING = 'clarity.oidc.pending'

const store = {
  get: (k: string) => { try { return sessionStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { sessionStorage.setItem(k, v) } catch { /* blocked */ } },
  del: (k: string) => { try { sessionStorage.removeItem(k) } catch { /* blocked */ } },
}

const b64url = (bytes: ArrayBuffer | Uint8Array) =>
  btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

function random(n = 32) {
  return b64url(crypto.getRandomValues(new Uint8Array(n)))
}

async function discover(issuer: string): Promise<Discovery> {
  const r = await fetch(`${issuer.replace(/\/$/, '')}/.well-known/openid-configuration`)
  if (!r.ok) throw new Error(`Identity provider discovery failed (${r.status})`)
  return r.json()
}

const redirectUri = () => `${location.origin}${location.pathname}`
/** Navigation seam (jsdom cannot stub location.assign). */
export const nav = { go: (url: string) => location.assign(url) }

export async function login(cfg: OidcConfig) {
  const d = await discover(cfg.issuer)
  const verifier = random(48), state = random(16), nonce = random(16)
  const challenge = b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)))
  store.set(PENDING, JSON.stringify({ verifier, state, token_endpoint: d.token_endpoint, client_id: cfg.client_id }))
  const url = new URL(d.authorization_endpoint)
  Object.entries({ response_type: 'code', client_id: cfg.client_id, redirect_uri: redirectUri(), scope: cfg.scope,
    code_challenge: challenge, code_challenge_method: 'S256', state, nonce }).forEach(([k, v]) => url.searchParams.set(k, v))
  nav.go(url.toString())
}

/** Completes a redirect back from the IdP. Returns true if a sign-in was completed. */
export async function handleCallback(): Promise<boolean> {
  const params = new URLSearchParams(location.search)
  const code = params.get('code'), state = params.get('state')
  if (!code || !state) return false
  const pending = JSON.parse(store.get(PENDING) ?? 'null')
  store.del(PENDING)
  history.replaceState(null, '', redirectUri())   // never leave the code in the address bar or history
  if (!pending || pending.state !== state) throw new Error('Sign-in failed: state mismatch. Please try again.')
  const r = await fetch(pending.token_endpoint, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: redirectUri(), client_id: pending.client_id, code_verifier: pending.verifier }),
  })
  if (!r.ok) throw new Error(`Sign-in failed (${r.status}).`)
  const t = await r.json()
  store.set(TOKEN, JSON.stringify({ access_token: t.access_token, expires_at: Date.now() + (Number(t.expires_in) || 3600) * 1000 }))
  return true
}

export function accessToken(): string | null {
  const t = JSON.parse(store.get(TOKEN) ?? 'null')
  if (!t) return null
  if (Date.now() > t.expires_at - 30_000) { store.del(TOKEN); return null }
  return t.access_token
}

export function logout() { store.del(TOKEN) }
