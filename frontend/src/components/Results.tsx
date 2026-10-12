import type { Evidence, Result, Risk } from '../types'

const LEVEL: Record<string, { bar: string; badge: string }> = {
  low: { bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  moderate: { bar: 'bg-amber-500', badge: 'bg-amber-50 text-amber-700 ring-amber-200' },
  high: { bar: 'bg-red-500', badge: 'bg-red-50 text-red-700 ring-red-200' },
}

function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: string }) {
  return (
    <div className="border-t border-slate-100 pt-5">
      <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">{title}</h3>{right && <span className="label">{right}</span>}</div>
      {children}
    </div>
  )
}

function RiskCard({ r }: { r: Risk }) {
  if (!r.available) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-3.5">
        <div className="flex items-center justify-between"><b className="text-sm">{r.disease} risk</b><span className="label">not run</span></div>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-500">{r.message}</p>
      </div>
    )
  }
  const lv = LEVEL[r.level ?? 'low']
  const pct = Math.round((r.probability ?? 0) * 100)
  return (
    <div className="rounded-xl border border-slate-200 p-3.5">
      <div className="flex items-center justify-between">
        <b className="text-sm">{r.disease} risk</b>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ring-1 ring-inset ${lv.badge}`}>{r.level}</span>
      </div>
      <div className="mt-2 flex items-end gap-2"><span className="text-3xl font-bold tabular-nums">{pct}%</span><span className="pb-1 text-xs text-slate-500">model signal</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${r.disease} risk`}>
        <div className={`h-full rounded-full ${lv.bar}`} style={{ width: `${pct}%` }} />
      </div>
      {r.drivers && r.drivers.length > 0 && (
        <p className="mt-2 text-xs text-slate-600"><span className="font-medium">Main drivers:</span> {r.drivers.map(d => `${d.feature} (${d.effect})`).join(', ')}</p>
      )}
      {r.metrics && <p className="mt-1 font-mono text-[10px] text-slate-400">holdout AUC {r.metrics.holdout_roc_auc} · CV AUC {r.metrics.cv_roc_auc_mean} · n={r.metrics.rows}</p>}
      {r.caveat && <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">{r.caveat}</p>}
    </div>
  )
}

function EvidenceChip({ id, items }: { id: string; items: Evidence[] }) {
  const ev = items.find(e => e.id === id)
  return <a href={`#ev-${id}`} title={ev?.title} className="rounded bg-brand-50 px-1.5 py-0.5 font-mono text-[10px] text-brand-700 ring-1 ring-brand-100 hover:bg-brand-100">{id}</a>
}

export default function Results({ result, busy }: { result: Result | null; busy: boolean }) {
  if (!result) {
    return (
      <section className="card flex min-h-[420px] flex-col items-center justify-center p-8 text-center">
        <div className="text-4xl text-brand-500">✳</div>
        <h2 className="mt-3 text-lg font-semibold">{busy ? 'The agent is working…' : 'Your clinical overview will appear here'}</h2>
        <p className="mt-1 max-w-md text-sm text-slate-500">Upload a report or add notes. The agent understands the patient, fetches guideline and PubMed evidence, then proposes conditions, a risk score and next steps.</p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-xs font-medium text-slate-600">
          <span className="chip">1 Understand</span>→<span className="chip">2 Fetch evidence</span>→<span className="chip">3 Recommend</span>
        </div>
      </section>
    )
  }
  const top = result.risk_score
  const topLevel = top ? LEVEL[top.level] : null
  const tags = [...result.medications, ...result.risk_factors]
  return (
    <section className="card space-y-5 p-5" aria-live="polite">
      <div className="flex items-center justify-between"><h2 className="text-base font-semibold">2 · Clinical overview</h2>
        <span className="label">{result.document_name ? `${result.input_modality} · ${result.document_name}` : result.input_modality ?? 'text'}</span></div>

      {result.urgent_attention && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3.5 text-sm text-red-800"><b>Urgent attention signal.</b> Potential emergency warning signs were identified. Use clinical judgment and local emergency protocols.</div>
      )}
      {result.llm_errors && result.llm_errors.length > 0 && (
        <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><b>The OpenAI call failed, so rules mode was used.</b> {result.llm_errors.join(' · ')}</div>
      )}
      {result.image_note && <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{result.image_note}</div>}

      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <div>
          <p className="label">Agent summary {result.llm_used ? '· LLM, evidence-cited' : '· rule-based'}</p>
          <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-slate-700">{result.summary}</p>
        </div>
        <div className="flex min-w-[130px] flex-col items-center justify-center rounded-xl bg-slate-50 p-4 text-center">
          <span className="label">Overall risk score</span>
          {top ? <>
            <span className="mt-1 text-4xl font-bold tabular-nums">{Math.round(top.value * 100)}</span>
            <span className={`mt-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ring-1 ring-inset ${topLevel?.badge}`}>{top.level} · {top.disease}</span>
          </> : <span className="mt-2 text-2xl text-slate-300">—</span>}
        </div>
      </div>

      <Section title="Risk prediction (tabular ML)" right="logistic regression"><div className="grid gap-3 md:grid-cols-2">{result.risks.map(r => <RiskCard key={r.key} r={r} />)}</div></Section>

      <Section title="Possible conditions" right="suggestions, not diagnoses">
        {result.possible_conditions.length ? (
          <ul className="space-y-2">
            {result.possible_conditions.map(c => (
              <li key={c.condition} className="rounded-xl border border-slate-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <b className="text-sm">{c.condition}</b>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${c.likelihood === 'stronger match' ? 'bg-brand-100 text-brand-900 ring-brand-200' : 'bg-slate-50 text-slate-600 ring-slate-200'}`}>{c.likelihood}</span>
                </div>
                <p className="mt-1 text-xs text-slate-600">Supported by: {c.supporting_findings.join(', ')}</p>
                {c.evidence_ids.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1.5">{c.evidence_ids.map(id => <EvidenceChip key={id} id={id} items={result.evidence} />)}</div>}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-slate-500">Not enough findings to suggest a condition.</p>}
      </Section>

      <Section title="Extracted from the record">
        <div className="grid gap-3 sm:grid-cols-3">
          {([['Symptoms', result.symptoms], ['Conditions', result.conditions], ['Medications & risk factors', tags]] as [string, string[]][]).map(([t, items]) => (
            <div key={t}><p className="label mb-1.5">{t}</p><div className="flex flex-wrap gap-1.5">{items.length ? items.map(x => <span className="chip" key={x}>{x}</span>) : <span className="text-xs text-slate-400">None detected</span>}</div></div>
          ))}
        </div>
        {Object.keys(result.vitals).length > 0 && <p className="mt-3 font-mono text-[11px] text-slate-500">{Object.entries(result.vitals).map(([k, v]) => `${k.replace('_', ' ')}: ${v}`).join(' · ')}</p>}
      </Section>

      {result.labs && result.labs.length > 0 && (
        <Section title="Lab findings" right="parsed from the report">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead><tr className="label"><th className="py-1 pr-3 font-normal">Test</th><th className="pr-3 font-normal">Result</th><th className="pr-3 font-normal">Reference</th><th className="font-normal">Flag</th></tr></thead>
              <tbody>{result.labs.map((l, i) => (
                <tr key={i} className="border-t border-slate-100"><td className="py-1.5 pr-3">{l.test}</td><td className="pr-3 tabular-nums">{l.value} {l.unit}</td><td className="pr-3 text-slate-500">{l.reference ?? '—'}</td>
                  <td><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${l.flag === 'high' || l.flag === 'low' ? 'bg-red-50 text-red-700 ring-red-200' : l.flag === 'borderline' ? 'bg-amber-50 text-amber-700 ring-amber-200' : 'bg-slate-50 text-slate-500 ring-slate-200'}`}>{l.flag}</span></td></tr>))}</tbody>
            </table>
          </div>
        </Section>
      )}

      <Section title="Recommended actions" right="for clinician review">
        <ol className="space-y-2.5">
          {result.recommended_actions.map((a, i) => (
            <li key={i} className="flex gap-3 text-sm">
              <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700">{i + 1}</span>
              <div><p>{a.action}</p><p className="text-xs text-slate-500">{a.rationale}</p>
                {a.evidence_ids.length > 0 && <div className="mt-1 flex flex-wrap gap-1.5">{a.evidence_ids.map(id => <EvidenceChip key={id} id={id} items={result.evidence} />)}</div>}</div>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Supporting evidence" right={`${result.evidence.length} sources`}>
        <div className="space-y-2.5">
          {result.evidence.map(e => (
            <article id={`ev-${e.id}`} key={e.id} className="scroll-mt-4 rounded-xl border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${e.kind === 'pubmed' ? 'bg-sky-50 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>{e.kind === 'pubmed' ? 'PubMed' : 'Guideline'}</span>
                <b className="text-sm">{e.title}</b>
              </div>
              <p className="mt-0.5 text-xs text-slate-500">{e.source}{e.relevance != null && ` · relevance ${e.relevance}`}</p>
              <p className="mt-1.5 line-clamp-4 text-xs leading-relaxed text-slate-700">{e.text}</p>
              {e.url && <a className="mt-1.5 inline-block text-xs font-medium text-brand-700 hover:underline" href={e.url} target="_blank" rel="noreferrer">Open source ↗</a>}
            </article>
          ))}
          {!result.evidence.length && <p className="text-sm text-slate-500">No relevant source found.</p>}
        </div>
      </Section>

      <Section title="Agent workflow" right="LangChain pipeline">
        <ol className="grid gap-2 md:grid-cols-3">
          {result.agent_trace.map(t => (
            <li key={t.step} className="rounded-xl bg-slate-50 p-3">
              <p className="text-sm font-semibold">{t.step}</p><p className="mt-0.5 text-xs text-slate-600">{t.detail}</p>
              <p className="mt-1 font-mono text-[10px] text-slate-400">{t.tools.join(' · ')} · {t.ms} ms</p>
            </li>
          ))}
        </ol>
      </Section>

      <p className="rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-500">ⓘ {result.disclaimer}</p>
    </section>
  )
}
