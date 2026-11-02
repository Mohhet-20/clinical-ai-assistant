import {
  Activity, AlertOctagon, BookOpen, Braces, Download, ExternalLink, FileJson, FlaskConical, GitBranch, Highlighter, Lock, Pill,
  Printer, ShieldAlert, ShieldCheck, Sparkles, Stethoscope, ThumbsDown, ThumbsUp, Workflow,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { ApiError, fhirBundle, sendFeedback } from '../api'
import type { Evidence, Feedback, Result, Risk, Verdict } from '../types'
import { EgfrScale, News2Bars, SignalMeter } from './Charts'
import Explain from './Explain'
import { PipelineProgress, PipelineTrace } from './Pipeline'
import { Medications } from './Scores'
import { Panel, StatusBadge, Tabs, levelDot, riskLevel, useToast } from './ui'

type Tab = 'overview' | 'explain' | 'scores' | 'evidence' | 'pipeline' | 'export'
const CAT_COLOR: Record<string, string> = { Symptoms: '#2a78d6', Conditions: '#eb6834', Medications: '#1baf7a', 'Risk factors': '#6250d6' }
const VITAL_LABEL: Record<string, [string, string]> = {
  age: ['Age', 'y'], systolic: ['Systolic', 'mmHg'], diastolic: ['Diastolic', 'mmHg'], heart_rate: ['Heart rate', '/min'], respiratory_rate: ['Resp. rate', '/min'],
  spo2: ['SpO₂', '%'], temperature: ['Temp', '°C'], glucose: ['Glucose', 'mg/dL'], hba1c: ['HbA1c', '%'], bmi: ['BMI', 'kg/m²'], cholesterol: ['Cholesterol', 'mg/dL'], creatinine: ['Creatinine', 'mg/dL'],
}

/** Clinician verdict on one suggestion, recorded in the server's audit trail against the analysis request id. */
function Review({ requestId, target, item, disabled }: { requestId?: string; target: Feedback['target']; item: string; disabled?: boolean }) {
  const [state, setState] = useState<{ verdict?: Verdict; status: 'idle' | 'saving' | 'saved' | 'error' }>({ status: 'idle' })
  const toast = useToast()
  if (!requestId || disabled) return null
  async function send(verdict: Verdict) {
    setState({ verdict, status: 'saving' })
    try { await sendFeedback({ request_id: requestId!, target, item, verdict }); setState({ verdict, status: 'saved' }); toast('Review recorded in the audit trail') }
    catch (e) { setState({ verdict, status: 'error' }); toast(e instanceof Error ? e.message : 'Review not recorded', 'error') }
  }
  const btn = (v: Verdict, Icon: typeof ThumbsUp, label: string) => (
    <button type="button" disabled={state.status === 'saving'} onClick={() => send(v)} aria-pressed={state.verdict === v} aria-label={label} title={label}
      className={`rounded-md p-1 transition ${state.verdict === v ? 'bg-action text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}><Icon className="h-3.5 w-3.5" /></button>
  )
  return <span className="inline-flex items-center gap-0.5 print:hidden" aria-label={`Review: ${item}`}>{btn('agree', ThumbsUp, 'Agree')}{btn('disagree', ThumbsDown, 'Disagree')}</span>
}

function download(name: string, data: unknown, type: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type }))
  Object.assign(document.createElement('a'), { href: url, download: name }).click()
  URL.revokeObjectURL(url)
}

function EvidenceChip({ id, items, onOpen }: { id: string; items: Evidence[]; onOpen: () => void }) {
  const ev = items.find(e => e.id === id)
  return <button type="button" onClick={onOpen} title={ev?.title} className="rounded bg-brand-50 px-1.5 py-0.5 font-mono text-[10px] text-brand-700 ring-1 ring-brand-100 transition hover:bg-brand-100">{id}</button>
}

// ---------------------------------------------------------------- overview pieces
function Triage({ result }: { result: Result }) {
  if (result.urgent_attention) {
    return (
      <div role="alert" className="animate-fade-up rounded-2xl border border-red-200 bg-red-50 p-4">
        <div className="flex items-start gap-3">
          <AlertOctagon className="mt-0.5 h-5 w-5 flex-none text-status-critical" />
          <div className="min-w-0">
            <p className="font-semibold text-red-900">Urgent attention signal</p>
            <p className="text-sm text-red-800">Potential emergency warning signs were identified. Use clinical judgement and local emergency protocols.</p>
            {!!result.urgent_reasons?.length && (
              <ul className="mt-2 flex flex-wrap gap-1.5">{result.urgent_reasons.map(r => <li key={r} className="rounded-full bg-surface/70 px-2.5 py-1 text-xs font-medium text-red-900 ring-1 ring-red-200">{r}</li>)}</ul>
            )}
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
      <ShieldCheck className="h-5 w-5 flex-none text-status-good" />
      <span><b>No urgent signals detected by automated screening.</b> <span className="text-slate-500">This is not reassurance: undocumented findings cannot be screened.</span></span>
    </div>
  )
}

function Kpis({ result }: { result: Result }) {
  const n2 = result.scores?.news2, qs = result.scores?.qsofa, eg = result.scores?.egfr
  const top = result.risks.filter(r => r.available).sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0]
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div className="col-span-2 rounded-2xl border border-slate-200 p-4 lg:col-span-1">
        <p className="label">NEWS2 early warning</p>
        {n2 ? <>
          <p className="mt-1 text-5xl font-bold leading-none text-slate-900">{n2.score}{!n2.complete && <span className="text-3xl text-slate-400" title="Incomplete: lower bound">+</span>}</p>
          <StatusBadge level={riskLevel(n2.risk)} className="mt-2">{n2.risk} clinical risk</StatusBadge>
          {n2.note && <p className="mt-2 text-[11px] leading-snug text-amber-700">{n2.note}</p>}
        </> : <p className="mt-2 text-sm text-slate-400">–</p>}
      </div>
      <div className="rounded-2xl border border-slate-200 p-4">
        <p className="label">qSOFA</p>
        <p className="mt-1 text-3xl font-bold text-slate-900">{qs?.score ?? '–'}<span className="text-lg text-slate-400">/3</span></p>
        {qs && <StatusBadge level={qs.positive ? 'critical' : qs.complete ? 'good' : 'neutral'} className="mt-2">{qs.positive ? 'positive' : qs.complete ? 'negative' : 'incomplete'}</StatusBadge>}
      </div>
      <div className="rounded-2xl border border-slate-200 p-4">
        <p className="label">eGFR · CKD-EPI 2021</p>
        {eg?.value != null ? <>
          <p className="mt-1 text-3xl font-bold text-slate-900">{eg.value}<span className="ml-1 text-xs font-normal text-slate-500">mL/min</span></p>
          <StatusBadge level={eg.value < 30 ? 'critical' : eg.value < 60 ? 'serious' : 'good'} className="mt-2">category {eg.stage}</StatusBadge>
        </> : <p className="mt-2 text-xs text-slate-500">{eg?.note ?? 'No creatinine documented'}</p>}
      </div>
      <div className="col-span-2 rounded-2xl border border-slate-200 p-4 lg:col-span-1">
        <p className="label">Highest model signal</p>
        {top ? <>
          <p className="mt-1 text-3xl font-bold text-slate-900">{Math.round((top.probability ?? 0) * 100)}<span className="text-lg text-slate-400">%</span></p>
          <p className="mb-2 text-xs text-slate-500">{top.disease} · research model, not a personal risk</p>
          <SignalMeter value={top.probability ?? 0} level={riskLevel(top.level === 'moderate' ? 'low-medium' : top.level)} label={`${top.disease} model signal`} />
        </> : <p className="mt-2 text-xs text-slate-500">Not enough inputs to run either model.</p>}
      </div>
    </div>
  )
}

function RiskCard({ r }: { r: Risk }) {
  if (!r.available) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-3.5">
        <div className="flex items-center justify-between"><b className="text-sm text-slate-900">{r.disease} model</b><span className="label">not run</span></div>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-500">{r.message}</p>
      </div>
    )
  }
  const pct = Math.round((r.probability ?? 0) * 100)
  return (
    <div className="rounded-xl border border-slate-200 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <b className="text-sm text-slate-900">{r.disease} model</b>
        <StatusBadge level={riskLevel(r.level === 'moderate' ? 'low-medium' : r.level)}>{r.level} · {pct}%</StatusBadge>
      </div>
      <div className="mt-3"><SignalMeter value={r.probability ?? 0} level={riskLevel(r.level === 'moderate' ? 'low-medium' : r.level)} label={`${r.disease} model signal`} /></div>
      {!!r.drivers?.length && <p className="mt-2 text-xs text-slate-600"><span className="font-medium">Drivers:</span> {r.drivers.map(d => `${d.feature} ${d.effect === 'raises' ? '↑' : '↓'}`).join(' · ')}</p>}
      {r.reliability === 'low' && (
        <p className="mt-2 rounded-lg bg-amber-50 px-2 py-1 text-[11px] text-amber-800 ring-1 ring-inset ring-amber-200">
          <b>Low reliability.</b> {r.out_of_range?.length ? `Outside training range: ${r.out_of_range.join('; ')}.` : 'Most inputs were imputed.'}
        </p>
      )}
      {r.metrics && <p className="mt-2 font-mono text-[10px] text-slate-400">AUC {r.metrics.holdout_roc_auc} · sens {r.metrics.holdout_sensitivity ?? '–'} · spec {r.metrics.holdout_specificity ?? '–'} · Brier {r.metrics.holdout_brier ?? '–'}</p>}
      {r.caveat && <details className="mt-1.5 text-[11px] text-slate-500"><summary className="cursor-pointer">Caveats</summary><p className="mt-1 leading-relaxed">{r.caveat}</p></details>}
    </div>
  )
}

// ---------------------------------------------------------------- main
export default function Results({ result, busy, onOpenModels }: { result: Result | null; busy: boolean; onOpenModels?: () => void }) {
  const [tab, setTab] = useState<Tab>('overview')
  const [fhir, setFhir] = useState<Record<string, unknown> | null>(null)
  const toast = useToast()
  useEffect(() => { setTab('overview'); setFhir(null) }, [result])

  const fhirCounts = useMemo(() => {
    const entries = (fhir?.entry as { resource: { resourceType: string } }[] | undefined) ?? []
    return Object.entries(entries.reduce<Record<string, number>>((m, e) => ({ ...m, [e.resource.resourceType]: (m[e.resource.resourceType] ?? 0) + 1 }), {}))
  }, [fhir])

  if (busy) return <PipelineProgress />
  if (!result) return <EmptyState />

  const live = !result.demo
  const openEvidence = () => setTab('evidence')
  async function loadFhir() {
    try { setFhir(await fhirBundle(result!)) }
    catch (e) { toast(e instanceof ApiError && e.requestId ? `${e.message} (ref ${e.requestId})` : e instanceof Error ? e.message : 'FHIR export failed', 'error') }
  }
  const groups: [string, string[]][] = [['Symptoms', result.symptoms], ['Conditions', result.conditions], ['Medications', result.medications], ['Risk factors', result.risk_factors]]
  const vitals = Object.entries(result.vitals).filter(([k]) => k !== 'sex')

  return (
    <section className="card overflow-hidden" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900"><Stethoscope className="h-4 w-4 text-brand-600" />Clinical overview</h2>
          <p className="truncate font-mono text-[10px] text-slate-500">{result.document_name ? `${result.input_modality} · ${result.document_name}` : result.input_modality ?? 'text'} · ref {result.request_id ?? '–'}{result.case_id && ' · saved to case history'}</p>
        </div>
        <div className="flex items-center gap-1.5 print:hidden">
          <button type="button" className="btn-secondary" onClick={() => { setTab('export'); if (!fhir && live) loadFhir() }}><Braces className="h-3.5 w-3.5" />FHIR</button>
          <button type="button" className="btn-secondary" onClick={() => download(`clarity-${result.request_id ?? 'analysis'}.json`, result, 'application/json')}><Download className="h-3.5 w-3.5" />JSON</button>
          <button type="button" className="btn-secondary" onClick={() => window.print()} aria-label="Print report"><Printer className="h-3.5 w-3.5" /></button>
        </div>
      </div>

      <div className="px-4 pt-2 sm:px-5">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[
          { id: 'overview', label: 'Overview', icon: <Activity className="h-3.5 w-3.5" /> },
          { id: 'explain', label: 'Explain', icon: <Highlighter className="h-3.5 w-3.5" />, count: result.annotations?.filter(a => a.kind === 'finding').length },
          { id: 'scores', label: 'Scores', icon: <Workflow className="h-3.5 w-3.5" /> },
          { id: 'evidence', label: 'Evidence', icon: <BookOpen className="h-3.5 w-3.5" />, count: result.evidence.length },
          { id: 'pipeline', label: 'Pipeline', icon: <GitBranch className="h-3.5 w-3.5" /> },
          { id: 'export', label: 'Export', icon: <FileJson className="h-3.5 w-3.5" /> },
        ]} />
      </div>

      <div className="space-y-4 p-4 sm:p-5" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {result.demo && (
          <div className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 flex-none" />
            <span><b>Offline demo.</b> This is a precomputed output of the real pipeline for this sample, shown because the server is still waking up. Live analysis resumes automatically.</span>
          </div>
        )}

        {tab === 'overview' && <>
          <Triage result={result} />
          {!!result.guardrails?.input_flags?.length && (
            <div role="alert" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              <ShieldAlert className="mt-0.5 h-4 w-4 flex-none" />
              <span><b>The record contains text that looks like instructions to an AI model,</b> so the LLM was not used for this analysis (local rules only).
                <span className="block font-mono text-[10px]">{result.guardrails.input_flags.join(' · ')}</span></span>
            </div>
          )}
          {!!result.llm_errors?.length && <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900">LLM unavailable or rejected by guardrails; rules mode was used. {result.llm_errors.join(' · ')}</p>}
          {result.image_note && <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">{result.image_note}</p>}

          {result.scores && <Kpis result={result} />}

          <div className="rounded-2xl bg-gradient-to-br from-brand-50 to-transparent p-4 ring-1 ring-inset ring-brand-100">
            <p className="label flex items-center gap-1.5 text-brand-700"><Sparkles className="h-3 w-3" />Agent summary · {result.llm_used ? 'LLM, evidence-cited, guardrail-checked' : 'deterministic rules'}</p>
            <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-slate-700">{result.summary}</p>
          </div>

          <div className="grid gap-4">
            <Panel title="Possible conditions" icon={<Stethoscope className="h-4 w-4 text-slate-400" />} right={<span className="label">suggestions, not diagnoses</span>}>
              {result.possible_conditions.length ? (
                <ul className="space-y-2">
                  {result.possible_conditions.map(c => (
                    <li key={c.condition} className="rounded-xl border border-slate-200 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <b className="text-sm text-slate-900">{c.condition}</b>
                        <span className="flex flex-none items-center gap-1">
                          <Review requestId={result.request_id} target="condition" item={c.condition} disabled={!live} />
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${c.likelihood === 'stronger match' ? 'bg-brand-100 text-brand-900 ring-brand-200' : 'bg-slate-50 text-slate-600 ring-slate-200'}`}>{c.likelihood}</span>
                        </span>
                      </div>
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-100" aria-hidden><div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, c.score / 6 * 100)}%` }} /></div>
                      <p className="mt-1.5 text-xs text-slate-600">{c.supporting_findings.join(' · ')}</p>
                      {c.evidence_ids.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{c.evidence_ids.map(id => <EvidenceChip key={id} id={id} items={result.evidence} onOpen={openEvidence} />)}</div>}
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-slate-500">Not enough findings to suggest a condition.</p>}
            </Panel>

            <Panel title="Recommended actions" icon={<ShieldCheck className="h-4 w-4 text-slate-400" />} right={<span className="label">for clinician review</span>}>
              <ol className="space-y-3">
                {result.recommended_actions.map((a, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2"><p className="text-slate-800">{a.action}</p><Review requestId={result.request_id} target="action" item={a.action.slice(0, 300)} disabled={!live} /></div>
                      <p className="text-xs text-slate-500">{a.rationale}</p>
                      {a.evidence_ids.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{a.evidence_ids.map(id => <EvidenceChip key={id} id={id} items={result.evidence} onOpen={openEvidence} />)}</div>}
                    </div>
                  </li>
                ))}
              </ol>
            </Panel>
          </div>

          <Panel title="Risk models" icon={<FlaskConical className="h-4 w-4 text-slate-400" />}
            right={onOpenModels && <button type="button" className="btn-ghost" onClick={onOpenModels}>Model cards & calibration <ExternalLink className="h-3 w-3" /></button>}>
            <div className="grid gap-3 md:grid-cols-2">{result.risks.map(r => <RiskCard key={r.key} r={r} />)}</div>
          </Panel>

          <Panel title="Extracted from the record" icon={<Highlighter className="h-4 w-4 text-slate-400" />}
            right={<button type="button" className="btn-ghost" onClick={() => setTab('explain')}>See it in the note →</button>}>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {groups.map(([t, items]) => (
                <div key={t}>
                  <p className="label mb-1.5 flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: CAT_COLOR[t] }} />{t}</p>
                  <div className="flex flex-wrap gap-1.5">{items.length ? items.map(x => <span key={x} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">{x}</span>) : <span className="text-xs text-slate-400">None detected</span>}</div>
                </div>
              ))}
            </div>
            {vitals.length > 0 && (
              <dl className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                {vitals.map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-slate-50 px-3 py-2">
                    <dt className="text-[10px] uppercase tracking-wide text-slate-500">{VITAL_LABEL[k]?.[0] ?? k}</dt>
                    <dd className="font-semibold tabular-nums text-slate-900">{v}<span className="ml-0.5 text-[10px] font-normal text-slate-500">{VITAL_LABEL[k]?.[1]}</span></dd>
                  </div>
                ))}
              </dl>
            )}
          </Panel>

          {(!!result.medication_details?.length || result.allergies?.status === 'documented' || result.allergies?.status === 'nkda') && (
            <Panel title="Medications & allergies" icon={<Pill className="h-4 w-4 text-slate-400" />} right={<span className="label">reconcile with patient</span>}>
              <Medications meds={result.medication_details ?? []} allergies={result.allergies} />
            </Panel>
          )}

          {!!result.labs?.length && (
            <Panel title="Lab findings" right={<span className="label">parsed from the report</span>}>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead><tr className="label"><th className="py-1 pr-3 font-normal">Test</th><th className="pr-3 font-normal">Result</th><th className="pr-3 font-normal">Reference</th><th className="font-normal">Flag</th></tr></thead>
                  <tbody>{result.labs.map((l, i) => (
                    <tr key={i} className="border-t border-slate-100"><td className="py-1.5 pr-3 text-slate-800">{l.test}</td><td className="pr-3 tabular-nums">{l.value} {l.unit}</td><td className="pr-3 text-slate-500">{l.reference ?? '–'}</td>
                      <td><StatusBadge level={l.flag === 'high' || l.flag === 'low' ? 'critical' : l.flag === 'borderline' ? 'warning' : l.flag === 'normal' ? 'good' : 'neutral'}>{l.flag}</StatusBadge></td></tr>))}</tbody>
                </table>
              </div>
            </Panel>
          )}
        </>}

        {tab === 'explain' && (result.annotations && (result.analyzed_text ?? result.extracted_text)
          ? <Explain text={(result.analyzed_text ?? result.extracted_text)!} annotations={result.annotations} />
          : <p className="text-sm text-slate-500">This result has no explainability data (older API version).</p>)}

        {tab === 'scores' && result.scores && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title={`NEWS2 · ${result.scores.news2.score}${result.scores.news2.complete ? '' : '+'}`} right={<StatusBadge level={riskLevel(result.scores.news2.risk)}>{result.scores.news2.risk} risk</StatusBadge>}>
              <News2Bars components={result.scores.news2.components} vitals={result.vitals} />
              <p className="mt-3 text-xs text-slate-700"><b>Response:</b> {result.scores.news2.response}</p>
              {result.scores.news2.note && <p className="mt-1 text-xs text-amber-700">{result.scores.news2.note}</p>}
              <p className="mt-2 text-[10px] text-slate-400">{result.scores.news2.reference}</p>
            </Panel>
            <div className="space-y-4">
              <Panel title={`qSOFA · ${result.scores.qsofa.score}/3`} right={<StatusBadge level={result.scores.qsofa.positive ? 'critical' : 'good'}>{result.scores.qsofa.positive ? 'positive' : 'negative'}</StatusBadge>}>
                <ul className="space-y-1.5 text-sm">
                  {([['respiratory_rate_ge_22', 'Respiratory rate ≥ 22/min'], ['systolic_le_100', 'Systolic BP ≤ 100 mmHg'], ['altered_mentation', 'Altered mentation']] as const).map(([k, label]) => {
                    const v = result.scores!.qsofa.components[k]
                    return (
                      <li key={k} className="flex items-center gap-2">
                        <span className={`h-2.5 w-2.5 rounded-full ${v == null ? 'bg-slate-300' : levelDot(v ? 'critical' : 'good')}`} />
                        <span className="flex-1 text-slate-700">{label}</span>
                        <span className="text-xs font-medium text-slate-500">{v == null ? 'not documented' : v ? 'met' : 'not met'}</span>
                      </li>
                    )
                  })}
                </ul>
                <p className="mt-2 text-xs text-slate-600">{result.scores.qsofa.interpretation}</p>
              </Panel>
              <Panel title="eGFR · CKD-EPI 2021">
                {result.scores.egfr?.value != null ? <>
                  <p className="text-sm text-slate-700"><b className="text-2xl text-slate-900">{result.scores.egfr.value}</b> mL/min/1.73m² · category {result.scores.egfr.stage}</p>
                  <EgfrScale value={result.scores.egfr.value} />
                  <p className="mt-2 text-xs text-slate-600">{result.scores.egfr.interpretation}</p>
                </> : <p className="text-sm text-slate-500">{result.scores.egfr?.note ?? 'No creatinine documented.'}</p>}
              </Panel>
            </div>
          </div>
        )}

        {tab === 'evidence' && (
          <div className="space-y-2.5">
            {result.evidence.map(e => (
              <article id={`ev-${e.id}`} key={e.id} className="rounded-xl border border-slate-200 p-3.5 transition hover:border-brand-200">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${e.kind === 'pubmed' ? 'bg-sky-50 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>{e.kind === 'pubmed' ? 'PubMed' : 'Guideline'}</span>
                  <b className="text-sm text-slate-900">{e.title}</b>
                  <span className="font-mono text-[10px] text-slate-400">[{e.id}]</span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{e.source}{e.relevance != null && ` · relevance ${e.relevance}`}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-700">{e.text}</p>
                {e.url && <a className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline" href={e.url} target="_blank" rel="noreferrer">Open source <ExternalLink className="h-3 w-3" /></a>}
              </article>
            ))}
            {!result.evidence.length && <p className="text-sm text-slate-500">No relevant source found.</p>}
          </div>
        )}

        {tab === 'pipeline' && (
          <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
            <Panel title="Agent trace" icon={<GitBranch className="h-4 w-4 text-slate-400" />} right={<span className="label">LangChain LCEL</span>}><PipelineTrace trace={result.agent_trace} /></Panel>
            <div className="space-y-4">
              <Panel title="Privacy boundary" icon={<Lock className="h-4 w-4 text-slate-400" />}>
                <p className="text-xs text-slate-600">{result.privacy?.phi_redacted
                  ? <><b>{result.privacy.phi_redacted} identifier{result.privacy.phi_redacted === 1 ? '' : 's'}</b> ({result.privacy.categories.join(', ').toLowerCase()}) redacted before any external call.</>
                  : result.privacy?.note}</p>
              </Panel>
              <Panel title="Guardrails" icon={<ShieldCheck className="h-4 w-4 text-slate-400" />}>
                <ul className="space-y-1 text-xs text-slate-600">
                  <li>Prompt-injection screen: {result.guardrails?.input_flags.length ? <b className="text-amber-700">flagged, LLM skipped</b> : 'clear'}</li>
                  <li>Summary check: {result.guardrails?.summary_check ? (result.guardrails.summary_check.rejected ? 'rejected (directive language)' : 'passed') : 'not needed (rules mode)'}</li>
                </ul>
              </Panel>
              {result.provenance && (
                <Panel title="Provenance">
                  <div className="space-y-1 font-mono text-[10px] text-slate-600">
                    <div>service v{result.provenance.service_version}</div>
                    {Object.entries(result.provenance.models).map(([k, v]) => <div key={k}>{k}: {v}</div>)}
                    <div>retrieval: {result.provenance.retrieval}</div><div>evidence corpus: {result.provenance.evidence_corpus}</div>
                    <div>llm: {result.provenance.llm ?? 'none (rules mode)'}</div>
                  </div>
                </Panel>
              )}
            </div>
          </div>
        )}

        {tab === 'export' && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">Export this analysis as a <b>FHIR R4 Bundle</b>: LOINC-coded Observations, SNOMED-coded <i>provisional</i> Conditions, preliminary RiskAssessments, MedicationStatements, AllergyIntolerances, a DetectedIssue for urgent signals, and Device + Provenance. The Patient carries no identifiers.</p>
            {!live ? <p className="rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-900">FHIR conversion runs on the server; it becomes available once the live API is reachable.</p>
              : !fhir ? <button type="button" className="btn-primary" onClick={loadFhir}><Braces className="h-4 w-4" />Build FHIR bundle</button> : <>
                <div className="flex flex-wrap gap-2">{fhirCounts.map(([t, n]) => <span key={t} className="rounded-lg bg-slate-100 px-2.5 py-1 font-mono text-xs text-slate-700">{t} × {n}</span>)}</div>
                <div className="flex gap-2">
                  <button type="button" className="btn-primary" onClick={() => download(`clarity-${result.request_id ?? 'analysis'}.fhir.json`, fhir, 'application/fhir+json')}><Download className="h-4 w-4" />Download bundle</button>
                  <button type="button" className="btn-secondary" onClick={() => navigator.clipboard?.writeText(JSON.stringify(fhir, null, 2)).then(() => toast('FHIR bundle copied'))}>Copy JSON</button>
                </div>
                <pre className="max-h-96 overflow-auto rounded-xl bg-[#0f172a] p-4 font-mono text-[11px] leading-relaxed text-slate-200 dark:bg-[#0b1016]">{JSON.stringify(fhir, null, 2)}</pre>
              </>}
          </div>
        )}

        <p className="flex items-start gap-1.5 rounded-xl bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-500"><ShieldAlert className="mt-0.5 h-3 w-3 flex-none" />{result.disclaimer}</p>
      </div>
    </section>
  )
}

function EmptyState() {
  const items = [
    { Icon: Highlighter, t: 'See what it read', d: 'Every finding highlighted in the note: counted, negated or excluded, with the reason.' },
    { Icon: Activity, t: 'Published scores', d: 'NEWS2, qSOFA and eGFR computed from the vitals, with incomplete scores flagged.' },
    { Icon: BookOpen, t: 'Cited next steps', d: 'Guideline and PubMed evidence behind every suggestion, for clinician review.' },
    { Icon: Braces, t: 'Interoperable', d: 'One click to a FHIR R4 bundle with LOINC and SNOMED codes.' },
  ]
  return (
    <section className="card flex min-h-[460px] flex-col justify-center p-6 sm:p-10">
      <p className="label text-brand-600">Clinical overview</p>
      <h2 className="mt-1 text-xl font-semibold text-slate-900">Your analysis will appear here</h2>
      <p className="mt-1 max-w-md text-sm text-slate-500">Pick a sample case or paste a de-identified note. Results take about a second.</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {items.map(({ Icon, t, d }) => (
          <div key={t} className="rounded-xl border border-slate-200 p-3.5">
            <Icon className="h-4 w-4 text-brand-600" /><p className="mt-2 text-sm font-semibold text-slate-900">{t}</p><p className="text-xs leading-relaxed text-slate-500">{d}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
