import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { accessToken, handleCallback, login, nav } from './oidc'

const discovery = { authorization_endpoint: 'https://idp.test/authorize', token_endpoint: 'https://idp.test/token' }

describe('OIDC PKCE flow', () => {
  let assigned = ''
  beforeEach(() => {
    sessionStorage.clear()
    history.replaceState(null, '', '/')
    assigned = ''
    vi.spyOn(nav, 'go').mockImplementation((u: string) => { assigned = u })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('redirects with an S256 challenge and remembers state + verifier', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(discovery))))
    await login({ issuer: 'https://idp.test', client_id: 'spa', scope: 'openid profile' })
    const url = new URL(assigned)
    expect(url.origin + url.pathname).toBe('https://idp.test/authorize')
    expect(url.searchParams.get('code_challenge_method')).toBe('S256')
    expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/)
    const pending = JSON.parse(sessionStorage.getItem('clarity.oidc.pending')!)
    expect(pending.state).toBe(url.searchParams.get('state'))
    expect(pending.verifier.length).toBeGreaterThanOrEqual(43)
  })

  it('rejects a callback whose state does not match, and scrubs the code from the URL', async () => {
    sessionStorage.setItem('clarity.oidc.pending', JSON.stringify({ state: 'expected', verifier: 'v', token_endpoint: discovery.token_endpoint, client_id: 'spa' }))
    history.replaceState(null, '', '/?code=abc&state=attacker')
    await expect(handleCallback()).rejects.toThrow(/state mismatch/)
    expect(location.search).toBe('')
    expect(accessToken()).toBeNull()
  })

  it('exchanges the code with the verifier and stores an expiring token', async () => {
    sessionStorage.setItem('clarity.oidc.pending', JSON.stringify({ state: 's1', verifier: 'ver', token_endpoint: discovery.token_endpoint, client_id: 'spa' }))
    history.replaceState(null, '', '/?code=abc&state=s1')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: 'tok', expires_in: 600 })))
    vi.stubGlobal('fetch', fetchMock)
    expect(await handleCallback()).toBe(true)
    const body = fetchMock.mock.calls[0][1].body as URLSearchParams
    expect(body.get('code_verifier')).toBe('ver')
    expect(body.get('grant_type')).toBe('authorization_code')
    expect(accessToken()).toBe('tok')
    expect(location.search).toBe('')
  })
})
