import { useMemo, useState } from 'react'
import type { Annotation } from '../types'

const CATEGORY: Record<string, { label: string; color: string }> = {
  symptom: { label: 'Symptom', color: '#2a78d6' },
  condition: { label: 'Condition', color: '#eb6834' },
  medication: { label: 'Medication', color: '#1baf7a' },
  'risk factor': { label: 'Risk factor', color: '#6250d6' },
}
const STATUS_TEXT: Record<string, string> = { affirmed: 'Counted as present', negated: 'Excluded: negated', family: 'Excluded: relative, recorded as family history', ignored: 'Excluded: report boilerplate' }

function describe(a: Annotation) {
  if (a.kind === 'phi') return `Identifier (${a.label}): redacted before any external LLM or PubMed call`
  if (a.kind === 'measurement') return `Measurement parsed: ${a.label}`
  return `${a.label} · ${CATEGORY[a.category ?? '']?.label ?? 'Finding'} · ${STATUS_TEXT[a.status ?? 'affirmed']}${a.reason ? ` (${a.reason})` : ''}${a.expanded ? ` · abbreviation for "${a.expanded}"` : ''}`
}

function Mark({ a, text, active, onHover, onPin }: { a: Annotation; text: string; active: boolean; onHover: (a: Annotation | null) => void; onPin: (a: Annotation) => void }) {
  // hover/focus preview; click or tap pins (touch screens have no hover)
  const common = { tabIndex: 0, title: describe(a), onMouseEnter: () => onHover(a), onFocus: () => onHover(a), onMouseLeave: () => onHover(null), onBlur: () => onHover(null), onClick: () => onPin(a) }
  const ring = active ? 'ring-2 ring-slate-900/30' : ''
  if (a.kind === 'phi') {
    return <mark {...common} className={`rounded bg-[#1e293b] px-1 text-[0.85em] font-medium text-white outline-none dark:bg-[#3b4a5e] ${ring}`} aria-label={`redacted ${a.label}`}><span className="mr-1 font-mono text-[9px] uppercase opacity-70">{a.label}</span>{text}</mark>
  }
  if (a.kind === 'measurement') {
    return <mark {...common} className={`rounded bg-slate-100 px-0.5 font-mono text-[0.9em] text-slate-800 outline-none ring-1 ring-inset ring-slate-200 ${ring}`}>{text}</mark>
  }
  const color = CATEGORY[a.category ?? '']?.color ?? '#64748b'
  const included = a.status === 'affirmed'
  return (
    <mark {...common} className={`rounded-sm px-0.5 text-slate-900 outline-none ${included ? '' : 'text-slate-400 line-through decoration-slate-500 decoration-2'} ${ring}`}
      style={included ? { background: `${color}26`, boxShadow: `inset 0 -2px 0 ${color}` } : { background: 'transparent', boxShadow: `inset 0 -1px 0 ${color}66` }}>
      {text}{a.expanded && <sup className="ml-0.5 font-mono text-[8px] text-slate-500 no-underline">abbr</sup>}
    </mark>
  )
}

/** The note exactly as analysed, with every decision the pipeline made shown in place. */
export default function Explain({ text, annotations }: { text: string; annotations: Annotation[] }) {
  const [hovered, setActive] = useState<Annotation | null>(null)
  const [pinned, setPinned] = useState<Annotation | null>(null)
  const active = hovered ?? pinned
  const parts = useMemo(() => {
    const out: (string | Annotation)[] = []
    let i = 0
    for (const a of annotations) {
      if (a.start < i) continue
      if (a.start > i) out.push(text.slice(i, a.start))
      out.push(a)
      i = a.end
    }
    out.push(text.slice(i))
    return out
  }, [text, annotations])
  const findings = annotations.filter(a => a.kind === 'finding')
  const counts = {
    present: findings.filter(a => a.status === 'affirmed').length,
    excluded: findings.filter(a => a.status !== 'affirmed').length,
    measurements: annotations.filter(a => a.kind === 'measurement').length,
    phi: annotations.filter(a => a.kind === 'phi').length,
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {([['Findings counted', counts.present], ['Findings excluded', counts.excluded], ['Measurements', counts.measurements], ['Identifiers redacted', counts.phi]] as const).map(([k, v]) => (
          <div key={k} className="rounded-xl bg-slate-50 px-3 py-2"><p className="text-xl font-bold text-slate-900">{v}</p><p className="text-[11px] text-slate-500">{k}</p></div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-slate-600" aria-label="Legend">
        {Object.entries(CATEGORY).map(([k, c]) => (
          <span key={k} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: c.color }} />{c.label}</span>
        ))}
        <span className="inline-flex items-center gap-1.5"><span className="text-slate-400 line-through">struck</span> excluded (negated, relative, boilerplate)</span>
        <span className="inline-flex items-center gap-1.5"><span className="rounded bg-slate-100 px-1 font-mono ring-1 ring-slate-200">12.3</span> measurement</span>
        <span className="inline-flex items-center gap-1.5"><span className="rounded bg-[#1e293b] px-1 font-mono text-[9px] text-white dark:bg-[#3b4a5e]">NAME</span> identifier</span>
      </div>

      <div className="max-h-[420px] overflow-y-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50/60 p-4 text-[15px] leading-8 text-slate-700">
        {parts.map((p, i) => typeof p === 'string' ? <span key={i}>{p}</span>
          : <Mark key={i} a={p} text={text.slice(p.start, p.end)} active={active === p} onHover={setActive} onPin={setPinned} />)}
      </div>

      <div aria-live="polite" className="min-h-[40px] rounded-xl border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-600">
        {active ? describe(active) : 'Tap, hover or focus any highlight to see why the pipeline counted or excluded it.'}
      </div>
    </div>
  )
}
