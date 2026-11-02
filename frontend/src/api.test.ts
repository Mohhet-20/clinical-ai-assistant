import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, analyze, apiKey } from './api'

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

describe('api client', () => {
  beforeEach(() => sessionStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('surfaces the server request id and a sign-in hint on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'Missing credentials.', request_id: 'req-12345678' }, 401)))
    const err = await analyze('thirst', {}, null).catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(401)
    expect(err.requestId).toBe('req-12345678')
    expect(err.message).toMatch(/Sign in/)
  })

  it('reports Retry-After on 429', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'Rate limit exceeded.' }, 429, { 'Retry-After': '17' })))
    await expect(analyze('x', {}, null)).rejects.toThrow(/17 seconds/)
  })

  it('flattens validation errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: [{ msg: 'String should have at most 30000 characters' }] }, 422)))
    await expect(analyze('x', {}, null)).rejects.toThrow('String should have at most 30000 characters')
  })

  it('prefers an SSO access token over a stored API key', async () => {
    apiKey.set('my-api-key')
    sessionStorage.setItem('clarity.oidc.token', JSON.stringify({ access_token: 'sso-token', expires_at: Date.now() + 600_000 }))
    const fetchMock = vi.fn().mockResolvedValue(json({}))
    vi.stubGlobal('fetch', fetchMock)
    await analyze('x', {}, null)
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer sso-token')
  })

  it('falls back to the API key once the token has expired', async () => {
    apiKey.set('my-api-key')
    sessionStorage.setItem('clarity.oidc.token', JSON.stringify({ access_token: 'old', expires_at: Date.now() - 1 }))
    const fetchMock = vi.fn().mockResolvedValue(json({}))
    vi.stubGlobal('fetch', fetchMock)
    await analyze('x', {}, null)
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer my-api-key')
  })

  it('sends files to /v1/upload as multipart without a JSON content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({}))
    vi.stubGlobal('fetch', fetchMock)
    await analyze('notes', { Glucose: 140 }, new File(['x'], 'r.txt', { type: 'text/plain' }))
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/v1\/upload$/)
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers['Content-Type']).toBeUndefined()
  })
})
