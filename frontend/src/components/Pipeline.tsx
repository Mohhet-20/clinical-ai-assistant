import { BookOpenCheck, Brain, Check, ClipboardList, Loader2, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { TraceStep } from '../types'

const STEPS = [
  { title: 'Understand the patient', detail: 'Redact identifiers · expand abbreviations · scope negation · parse vitals, labs, meds', Icon: Brain },
  { title: 'Fetch evidence', detail: 'FAISS search over curated guidelines · PubMed E-utilities', Icon: BookOpenCheck },
  { title: 'Recommend', detail: 'NEWS2 · qSOFA · eGFR · risk models · differential · guardrailed synthesis', Icon: ClipboardList },
]

/** Shown while a request is in flight. The server runs the steps in one call, so progress here is
 *  indicative only; the real per-step timings appear in the Pipeline tab afterwards. */
export function PipelineProgress() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setStep(s => Math.min(s + 1, STEPS.length - 1)), 900)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="card flex min-h-[460px] flex-col justify-center p-6 sm:p-10" aria-live="polite" aria-busy="true">
      <p className="label text-brand-600">Agent running</p>
      <h2 className="mt-1 text-xl font-semibold text-slate-900">Analysing the record…</h2>
      <ol className="mt-6 space-y-4">
        {STEPS.map((s, i) => {
          const state = i < step ? 'done' : i === step ? 'active' : 'todo'
          return (
            <li key={s.title} className={`flex items-start gap-3 transition-opacity ${state === 'todo' ? 'opacity-40' : ''}`}>
              <span className={`mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full ${state === 'done' ? 'bg-action text-white' : state === 'active' ? 'bg-brand-50 text-brand-700 ring-2 ring-brand-500' : 'bg-slate-100 text-slate-400'}`}>
                {state === 'done' ? <Check className="h-4 w-4" /> : state === 'active' ? <Loader2 className="h-4 w-4 animate-spin" /> : <s.Icon className="h-4 w-4" />}
              </span>
              <span><b className="text-sm text-slate-900">{i + 1}. {s.title}</b><span className="block text-xs text-slate-500">{s.detail}</span></span>
            </li>
          )
        })}
      </ol>
      <div className="mt-8 space-y-2"><div className="skeleton h-3 w-3/4" /><div className="skeleton h-3 w-1/2" /><div className="skeleton h-3 w-2/3" /></div>
    </div>
  )
}

/** The real agent trace returned by the API, as a timeline with proportional timing bars. */
export function PipelineTrace({ trace }: { trace: TraceStep[] }) {
  const total = Math.max(trace.reduce((s, t) => s + t.ms, 0), 1)
  return (
    <ol className="relative space-y-4 border-l border-slate-200 pl-6">
      {trace.map((t, i) => {
        const Icon = STEPS[i]?.Icon ?? ShieldCheck
        return (
          <li key={t.step} className="relative">
            <span className="absolute -left-[37px] flex h-6 w-6 items-center justify-center rounded-full bg-action text-white ring-4 ring-surface"><Icon className="h-3.5 w-3.5" /></span>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <b className="text-sm text-slate-900">{t.step}</b>
              <span className="font-mono text-[11px] tabular-nums text-slate-500">{t.ms} ms</span>
            </div>
            <p className="text-xs text-slate-600">{t.detail}</p>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden><div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.max(2, t.ms / total * 100)}%` }} /></div>
            <div className="mt-1.5 flex flex-wrap gap-1">{t.tools.map(x => <span key={x} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">{x}</span>)}</div>
          </li>
        )
      })}
    </ol>
  )
}
