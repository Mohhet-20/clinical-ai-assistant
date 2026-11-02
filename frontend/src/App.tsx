import {
  Activity, ArrowRight, BookOpen, Braces, ChevronDown, FlaskConical, Highlighter, KeyRound, Lock, Moon, ScrollText, ShieldCheck, Sun,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { API, ApiError, analyze, apiKey, getAuthConfig, getHealth, getMe } from './api'
import Cases from './components/Cases'
import Chat from './components/Chat'
import Intake from './components/Intake'
import Models from './components/Models'
import Results from './components/Results'
import { useTheme, useToast } from './components/ui'
import demoResults from './demo-results.json'
import { handleCallback, login, logout } from './oidc'
import type { Sample } from './samples'
import { SAMPLES } from './samples'
import type { AuthConfig, Health, Me, Result } from './types'

type Conn = 'checking' | 'online' | 'waking' | 'offline'
const DEMO = demoResults as unknown as Record<string, Result>
const WAKE_LIMIT_S = 120

function Logo() {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden><rect width="32" height="32" rx="8" fill="#237f67" /><path d="M16 7v18M7 16h18M9.6 9.6l12.8 12.8M22.4 9.6 9.6 22.4" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" /></svg>
      <b className="text-lg tracking-tight text-slate-900">clarity</b>
    </span>
  )
}

function StatusMenu({ conn, health, waited }: { conn: Conn; health: Health | null; waited: number }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const label = { checking: 'Connecting…', online: 'Operational', waking: `Waking server · ${waited}s`, offline: 'Offline · demo mode' }[conn]
  const dot = { checking: 'bg-slate-400 animate-pulse', online: 'bg-status-good', waking: 'bg-status-warning animate-pulse', offline: 'bg-status-critical' }[conn]
  const rows: [string, string][] = health ? [
    ['Version', health.version ?? '–'], ['Retrieval', `${health.vector_store.toUpperCase()} · ${health.embeddings}`], ['Evidence documents', String(health.evidence_documents)],
    ['LLM', health.llm_enabled ? 'configured' : 'rules mode'], ['PubMed', health.pubmed_live ? 'live' : 'off'], ['Auth', health.auth ?? '–'],
    ['Audit trail', health.audit_log ? 'on' : 'off'], ['PHI redaction', health.phi_redaction ? 'on' : 'off'], ['Case store', health.case_store ? 'encrypted' : 'off'],
    ['Risk models', Object.entries(health.models).map(([k, v]) => `${k} ${v ? '✓' : '✗'}`).join(' · ')],
  ] : []
  return (
    <div ref={ref} className="relative">
      <button type="button" data-conn={conn} className="btn-ghost rounded-full border border-slate-200 bg-surface" aria-expanded={open} aria-label={`Server status: ${label}`} onClick={() => setOpen(o => !o)}>
        <span className={`h-2 w-2 rounded-full ${dot}`} /><span className="hidden sm:inline">{label}</span><ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="card absolute right-0 z-30 mt-2 w-72 animate-fade-up p-4 text-xs">
          <p className="font-semibold text-slate-900">{label}</p>
          {conn === 'waking' && <p className="mt-1 text-slate-600">The free-tier API sleeps when idle and takes up to a minute to wake. Sample cases show precomputed results meanwhile.</p>}
          {rows.length > 0 && <dl className="mt-2 space-y-1">{rows.map(([k, v]) => <div key={k} className="flex justify-between gap-3"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-800">{v}</dd></div>)}</dl>}
          <a className="mt-3 inline-flex items-center gap-1 font-medium text-brand-700 hover:underline" href={`${API}/docs`} target="_blank" rel="noreferrer">OpenAPI docs <ArrowRight className="h-3 w-3" /></a>
        </div>
      )}
    </div>
  )
}

function Account({ config, me, onChange }: { config: AuthConfig | null; me: Me | null; onChange: () => void }) {
  const oidc = config?.oidc
  if (me && me.actor.startsWith('user:')) {
    return (
      <span className="flex items-center gap-2 text-xs text-slate-600">
        <span className="hidden md:inline" title={me.actor}>{me.name ?? 'Signed in'} · <span className="uppercase">{me.role}</span></span>
        <button type="button" className="btn-secondary" onClick={() => { logout(); onChange() }}>Sign out</button>
      </span>
    )
  }
  if (!oidc?.client_id) return null
  return <button type="button" className="btn-primary px-3 py-1.5 text-xs" onClick={() => login({ issuer: oidc.issuer, client_id: oidc.client_id!, scope: oidc.scope })}>Sign in</button>
}

function Settings({ authRequired }: { authRequired: boolean }) {
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState(apiKey.get())
  const toast = useToast()
  return (
    <div className="relative">
      <button type="button" className="btn-ghost" aria-expanded={open} aria-label="API key settings" onClick={() => setOpen(o => !o)}>
        <KeyRound className="h-4 w-4" />{authRequired && !key && <i className="h-1.5 w-1.5 rounded-full bg-status-warning" aria-label="API key needed" />}
      </button>
      {open && (
        <form className="card absolute right-0 z-30 mt-2 w-72 animate-fade-up p-4" onSubmit={e => { e.preventDefault(); apiKey.set(key.trim()); setOpen(false); toast(key.trim() ? 'API key saved for this tab' : 'API key cleared') }}>
          <label htmlFor="api-key" className="label mb-1.5 block">API key</label>
          <input id="api-key" className="input font-mono" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)}
            placeholder={authRequired ? 'Required by this server' : 'Not required by this server'} />
          <p className="mt-2 text-[11px] text-slate-500">Kept in this tab's session storage only, sent as a Bearer token. SSO users don't need one.</p>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => { setKey(''); apiKey.set('') }}>Clear</button>
            <button className="btn-primary px-3 py-1.5 text-xs">Save</button>
          </div>
        </form>
      )}
    </div>
  )
}

const CAPABILITIES = [
  { Icon: Highlighter, t: 'Explainable NLP', d: 'Every finding shown in the note: counted, negated, family history or boilerplate, with the reason.' },
  { Icon: Activity, t: 'Early-warning scores', d: 'NEWS2, qSOFA and eGFR from parsed vitals. Incomplete scores are shown as lower bounds.' },
  { Icon: BookOpen, t: 'Cited evidence', d: 'FAISS retrieval over guidelines plus live PubMed. Every action links to its source.' },
  { Icon: Braces, t: 'FHIR R4 export', d: 'LOINC Observations, SNOMED provisional Conditions, RiskAssessment, Provenance.' },
  { Icon: Lock, t: 'Privacy by design', d: 'Identifiers redacted before any LLM or PubMed call. Encrypted, expiring case store.' },
  { Icon: ShieldCheck, t: 'Governed', d: 'OIDC SSO, hash-chained audit trail, LLM guardrails, model cards and a CI quality gate.' },
]

function Hero({ onDemo, onModels, compact }: { onDemo: () => void; onModels: () => void; compact: boolean }) {
  if (compact) return null
  return (
    <section className="relative overflow-hidden border-b border-slate-200">
      <div className="hero-grid absolute inset-0" aria-hidden />
      <div className="relative mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:py-16 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <div className="animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-surface/80 px-3 py-1 text-xs font-medium text-brand-700">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />Explainable clinical AI · research prototype
          </span>
          <h1 className="mt-4 text-4xl font-bold leading-[1.05] tracking-tight text-slate-900 sm:text-5xl">
            Clinical notes in.<br /><span className="bg-gradient-to-r from-brand-600 to-sky-600 bg-clip-text text-transparent">Explainable, cited, auditable</span> decisions out.
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-600">
            Clarity reads notes, lab PDFs and images. It shows exactly which findings it counted or excluded and why, computes NEWS2, qSOFA and eGFR,
            cites guideline and PubMed evidence for each next step, and exports FHIR R4. Identifiers are redacted and every action is audited.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" className="btn-primary px-5 py-3 text-base" onClick={onDemo}>Run the deteriorating-patient case <ArrowRight className="h-4 w-4" /></button>
            <button type="button" className="btn-secondary px-4 py-3 text-sm" onClick={onModels}><FlaskConical className="h-4 w-4" />Model cards & calibration</button>
          </div>
          <p className="mt-3 text-xs text-slate-500">Not a medical device. Synthetic data only.</p>
        </div>
        <ul className="grid animate-fade-up gap-3 sm:grid-cols-2" style={{ animationDelay: '120ms' }}>
          {CAPABILITIES.map(({ Icon, t, d }) => (
            <li key={t} className="card p-4 transition hover:-translate-y-0.5 hover:shadow-lift">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><Icon className="h-4 w-4" /></span>
              <p className="mt-2.5 text-sm font-semibold text-slate-900">{t}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{d}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

export default function App() {
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [features, setFeatures] = useState<Record<string, string>>({})
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [conn, setConn] = useState<Conn>('checking')
  const [waited, setWaited] = useState(0)
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [authTick, setAuthTick] = useState(0)
  const [activeSample, setActiveSample] = useState<string | null>(null)
  const [modelsOpen, setModelsOpen] = useState(false)
  const { dark, toggle } = useTheme()
  const toast = useToast()
  const resultsRef = useRef<HTMLDivElement>(null)

  // Connection: detect a sleeping free-tier server quickly, then poll until it wakes.
  useEffect(() => {
    let cancelled = false
    const started = Date.now()
    const tick = setInterval(() => setWaited(Math.round((Date.now() - started) / 1000)), 1000)
    async function poll() {
      while (!cancelled) {
        try {
          const h = await getHealth(10_000)
          if (cancelled) return
          setHealth(h); setConn('online'); clearInterval(tick)
          getAuthConfig().then(setAuthConfig).catch(() => undefined)
          return
        } catch {
          if (cancelled) return
          setConn((Date.now() - started) / 1000 > WAKE_LIMIT_S ? 'offline' : 'waking')
          await new Promise(r => setTimeout(r, 4000))
        }
      }
    }
    poll()
    handleCallback().then(done => { if (done) setAuthTick(t => t + 1) }).catch(e => setError(e instanceof Error ? e.message : 'Sign-in failed'))
    return () => { cancelled = true; clearInterval(tick) }
  }, [])
  useEffect(() => { if (conn === 'online') getMe().then(setMe).catch(() => setMe(null)) }, [authTick, conn])
  useEffect(() => { if (conn === 'online' && result?.demo) toast('Server is awake: analyses now run live') }, [conn]) // eslint-disable-line react-hooks/exhaustive-deps

  const scrollToResults = () => setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)

  const run = useCallback(async (t: string, feats: Record<string, string>, f: File | null) => {
    setBusy(true); setError('')
    try {
      const numeric = Object.fromEntries(Object.entries(feats).filter(([, v]) => v.trim() !== '').map(([k, v]) => [k, Number(v)]))
      const r = await analyze(t, numeric, f)
      setResult(r)
      if (r.extracted_text) setText(r.extracted_text)
      setFile(null)
    } catch (e) {
      setError(e instanceof TypeError || (e instanceof DOMException && e.name === 'TimeoutError')
        ? 'The analysis server is unreachable or still waking up. Sample cases show precomputed results meanwhile.'
        : e instanceof ApiError && e.requestId ? `${e.message} (ref ${e.requestId})` : e instanceof Error ? e.message : 'Analysis failed')
    } finally { setBusy(false) }
  }, [])

  function runSample(s: Sample) {
    setText(s.text); setFeatures(s.features); setFile(null); setActiveSample(s.id); setError('')
    scrollToResults()
    if (conn === 'online') { run(s.text, s.features, null); return }
    const demo = DEMO[s.id]
    if (demo) { setResult({ ...demo, demo: true }); toast('Showing the offline demo while the server wakes') }
  }

  return (
    <div className="min-h-screen">
      <a href="#intake" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">Skip to the record</a>
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-surface/80 backdrop-blur-md print:static">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5">
          <div className="flex items-center gap-3"><Logo /><span className="label hidden md:inline">clinical decision support</span></div>
          <nav className="flex items-center gap-1 print:hidden" aria-label="Main">
            <button type="button" className="btn-ghost hidden sm:inline-flex" onClick={() => setModelsOpen(true)}><FlaskConical className="h-4 w-4" />Model cards</button>
            <a className="btn-ghost hidden sm:inline-flex" href={`${API}/docs`} target="_blank" rel="noreferrer"><ScrollText className="h-4 w-4" />API</a>
            <StatusMenu conn={conn} health={health} waited={waited} />
            <button type="button" className="btn-ghost" onClick={toggle} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>{dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</button>
            <Settings authRequired={!!health?.auth && health.auth !== 'disabled'} />
            <Account config={authConfig} me={me} onChange={() => setAuthTick(t => t + 1)} />
          </nav>
        </div>
        {conn === 'waking' && (
          <div className="border-t border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-900 print:hidden">
            Waking the analysis server ({waited}s; free tier, usually under a minute). Sample cases run instantly from precomputed results meanwhile.
          </div>
        )}
      </header>

      <Hero compact={!!result || busy} onModels={() => setModelsOpen(true)} onDemo={() => runSample(SAMPLES[0])} />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:py-8">
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,8fr)] print:block">
          <div className="min-w-0 space-y-6 print:hidden lg:sticky lg:top-20">
            <Intake text={text} setText={t => { setText(t); setActiveSample(null) }} file={file} setFile={setFile} features={features} setFeatures={setFeatures}
              busy={busy} error={error} onSubmit={() => { scrollToResults(); run(text, features, file) }} onSample={runSample} activeSample={activeSample} />
            <Chat context={text} />
            {health?.case_store && <Cases refreshKey={`${result?.request_id ?? ''}-${authTick}`} onOpen={r => { setResult(r); if (r.extracted_text) setText(r.extracted_text) }} />}
          </div>
          <div ref={resultsRef} className="min-w-0 scroll-mt-20"><Results result={result} busy={busy} onOpenModels={() => setModelsOpen(true)} /></div>
        </div>
      </main>

      <footer className="border-t border-slate-200 print:hidden">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <span className="flex items-center gap-2"><Logo /><span>Research prototype · not a medical device · not for emergencies or patient care.</span></span>
          <span className="flex gap-4">
            <a className="hover:text-slate-800" href={`${API}/docs`} target="_blank" rel="noreferrer">OpenAPI</a>
            <button type="button" className="hover:text-slate-800" onClick={() => setModelsOpen(true)}>Model cards</button>
            <a className="hover:text-slate-800" href={`${API}/v1/health`} target="_blank" rel="noreferrer">Health</a>
          </span>
        </div>
      </footer>
      <Models open={modelsOpen} onClose={() => setModelsOpen(false)} />
    </div>
  )
}
