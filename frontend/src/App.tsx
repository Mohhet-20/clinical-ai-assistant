import { useEffect, useState } from 'react'
import { analyze, getHealth } from './api'
import Chat from './components/Chat'
import Intake from './components/Intake'
import Results from './components/Results'
import type { Health, Result } from './types'

function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset ${ok ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-500 ring-slate-200'}`}><i className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-emerald-500' : 'bg-slate-400'}`} />{children}</span>
}

export default function App() {
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [features, setFeatures] = useState<Record<string, string>>({})
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => { getHealth().then(setHealth).catch(() => setOffline(true)) }, [])

  async function submit() {
    setBusy(true); setError('')
    try {
      const numeric = Object.fromEntries(Object.entries(features).filter(([, v]) => v.trim() !== '').map(([k, v]) => [k, Number(v)]))
      const r = await analyze(text, numeric, file)
      setResult(r)
      if (r.extracted_text) setText(r.extracted_text)
      setFile(null)
    } catch (e) {
      setError(e instanceof TypeError ? 'Cannot reach the API. Start the backend (uvicorn app.main:app) and check VITE_API_URL / CORS_ORIGINS.' : e instanceof Error ? e.message : 'Analysis failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-baseline gap-2"><span className="text-xl text-brand-600">✳</span><b className="text-lg tracking-tight">clarity</b><span className="label hidden sm:inline">clinical decision support</span></div>
          <div className="flex flex-wrap gap-1.5">
            {offline && <Pill ok={false}>API offline</Pill>}
            {health && <>
              <Pill ok>API online</Pill>
              <Pill ok>{health.vector_store.toUpperCase()} · {health.embeddings}</Pill>
              <Pill ok={health.llm_enabled}>{health.llm_enabled ? 'LLM configured' : 'Rules mode'}</Pill>
              <Pill ok={health.pubmed_live}>PubMed {health.pubmed_live ? 'live' : 'off'}</Pill>
            </>}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-8 max-w-2xl">
          <p className="label text-brand-600">Multimodal AI doctor assistant</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">A clearer view of the whole patient.</h1>
          <p className="mt-2 text-slate-600">Combine reports, symptoms and images. An agent extracts clinical facts, retrieves guideline and PubMed evidence, scores risk with ML models and drafts evidence-backed next steps for clinician review.</p>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className="space-y-6">
            <Intake text={text} setText={setText} file={file} setFile={setFile} features={features} setFeatures={setFeatures} busy={busy} error={error} onSubmit={submit} />
            <Chat context={text} />
          </div>
          <Results result={result} busy={busy} />
        </div>
        <footer className="mt-10 border-t border-slate-200 pt-4 text-xs text-slate-500">Educational research prototype · not a medical device · not for emergency or patient-care use.</footer>
      </main>
    </div>
  )
}
