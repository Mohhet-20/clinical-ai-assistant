import { useState } from 'react'

const KEY = 'clarity.consent.v1'
const accepted = () => { try { return sessionStorage.getItem(KEY) === 'yes' } catch { return false } }

/** Intended-use acknowledgement shown once per browser session before any data can be entered. */
export default function Consent({ children }: { children: React.ReactNode }) {
  const [ok, setOk] = useState(accepted)
  const [checked, setChecked] = useState(false)
  if (ok) return <>{children}</>
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="consent-title" className="card w-full max-w-lg p-6">
        <p className="label text-brand-600">Before you start</p>
        <h1 id="consent-title" className="mt-1 text-xl font-bold tracking-tight">Clarity is clinical decision <i>support</i>, not a decision-maker.</h1>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-slate-600">
          <li>It is a research prototype and is not a medical device. It does not diagnose, prescribe or triage.</li>
          <li>Every output must be verified against the source record, cited evidence and local protocols by a qualified clinician.</li>
          <li>Use synthetic or de-identified data. Identifiers are redacted before external calls, but redaction cannot be guaranteed complete.</li>
          <li>For emergencies, use local emergency services and established clinical pathways — never this tool.</li>
        </ul>
        <label className="mt-4 flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand-600" checked={checked} onChange={e => setChecked(e.target.checked)} />
          <span>I understand the intended use and will only enter synthetic or de-identified information.</span>
        </label>
        <button className="btn-primary mt-4 w-full" disabled={!checked}
          onClick={() => { try { sessionStorage.setItem(KEY, 'yes') } catch { /* storage blocked: ask again next load */ } setOk(true) }}>Continue</button>
      </div>
    </div>
  )
}
