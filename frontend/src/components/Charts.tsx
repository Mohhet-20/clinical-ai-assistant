import { useState } from 'react'
import type { Level } from './ui'

const FILL: Record<number, string> = { 1: 'bg-status-warning', 2: 'bg-status-serious', 3: 'bg-status-critical' }
const POINT_WORD = ['normal', 'mild', 'moderate', 'severe']

const NEWS2_ROWS: { key: string; label: string; value: (v: Record<string, number>) => string | null }[] = [
  { key: 'respiratory_rate', label: 'Respiration rate', value: v => v.respiratory_rate != null ? `${v.respiratory_rate}/min` : null },
  { key: 'spo2', label: 'SpO₂ (scale 1)', value: v => v.spo2 != null ? `${v.spo2}%` : null },
  { key: 'supplemental_oxygen', label: 'Air or oxygen', value: () => null },
  { key: 'systolic', label: 'Systolic BP', value: v => v.systolic != null ? `${v.systolic} mmHg` : null },
  { key: 'heart_rate', label: 'Pulse', value: v => v.heart_rate != null ? `${v.heart_rate}/min` : null },
  { key: 'consciousness', label: 'Consciousness', value: () => null },
  { key: 'temperature', label: 'Temperature', value: v => v.temperature != null ? `${v.temperature} °C` : null },
]

/** NEWS2 parameter chart: three cells per parameter, filled to its points (RCP 0-3), coloured by severity and labelled. */
export function News2Bars({ components, vitals }: { components: Record<string, number>; vitals: Record<string, number> }) {
  return (
    <table className="w-full text-xs">
      <caption className="sr-only">NEWS2 points by parameter</caption>
      <thead><tr className="label"><th className="pb-1.5 text-left font-normal">Parameter</th><th className="pb-1.5 text-left font-normal">Value</th><th className="pb-1.5 text-left font-normal">Points</th></tr></thead>
      <tbody>
        {NEWS2_ROWS.map(r => {
          const pts = components[r.key]
          const val = r.key === 'supplemental_oxygen' ? (pts == null ? null : pts ? 'oxygen' : 'air')
            : r.key === 'consciousness' ? (pts == null ? null : pts ? 'new confusion / CVPU' : 'alert') : r.value(vitals)
          return (
            <tr key={r.key} className="border-t border-slate-100" title={pts == null ? 'Not documented: counts as 0 in the lower-bound total' : `${pts} point${pts === 1 ? '' : 's'} (${POINT_WORD[pts]})`}>
              <td className="py-1.5 pr-2 text-slate-600">{r.label}</td>
              <td className="pr-2 tabular-nums text-slate-800">{val ?? <span className="italic text-slate-400">not documented</span>}</td>
              <td className="w-[112px]">
                {pts == null ? <span className="text-[11px] text-slate-400">–</span> : (
                  <span className="flex items-center gap-1.5">
                    <span className="flex gap-0.5" aria-hidden>
                      {[1, 2, 3].map(i => <span key={i} className={`h-2.5 w-5 rounded-[3px] ${i <= pts ? FILL[pts] : 'bg-slate-100'}`} />)}
                    </span>
                    <span className="font-semibold tabular-nums text-slate-800">{pts}</span>
                  </span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** Horizontal meter for a 0-1 model signal; fill carries severity, track is a quiet step of the same family. */
export function SignalMeter({ value, level, label }: { value: number; level: Level; label: string }) {
  const fill = level === 'critical' ? 'bg-status-critical' : level === 'serious' ? 'bg-status-serious' : level === 'warning' ? 'bg-status-warning' : 'bg-status-good'
  const pct = Math.round(value * 100)
  return (
    <div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className={`h-full rounded-full ${fill} transition-[width] duration-700`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-400"><span>0</span><span>0.5 threshold</span><span>1</span></div>
    </div>
  )
}

const STAGES = [{ s: 'G5', from: 0, to: 15 }, { s: 'G4', from: 15, to: 30 }, { s: 'G3b', from: 30, to: 45 }, { s: 'G3a', from: 45, to: 60 }, { s: 'G2', from: 60, to: 90 }, { s: 'G1', from: 90, to: 120 }]
const STAGE_FILL: Record<string, string> = { G5: 'bg-status-critical', G4: 'bg-status-critical/70', G3b: 'bg-status-serious', G3a: 'bg-status-warning', G2: 'bg-emerald-200', G1: 'bg-emerald-100' }

/** KDIGO GFR categories with a marker at the estimate. */
export function EgfrScale({ value }: { value: number }) {
  const x = Math.min(value, 120) / 120 * 100
  return (
    <div className="mt-2" aria-label={`eGFR ${value} on the KDIGO category scale`}>
      <div className="relative">
        <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full">
          {STAGES.map(g => <div key={g.s} className={STAGE_FILL[g.s]} style={{ width: `${(g.to - g.from) / 120 * 100}%` }} title={`${g.s}: ${g.from}–${g.to === 120 ? '≥90' : g.to}`} />)}
        </div>
        <div className="absolute -top-1 h-4.5 w-1 -translate-x-1/2 rounded-full bg-slate-900 ring-2 ring-surface" style={{ left: `${x}%`, height: 18 }} />
      </div>
      <div className="mt-1 flex font-mono text-[9px] text-slate-400">
        {STAGES.map(g => <span key={g.s} className="text-center" style={{ width: `${(g.to - g.from) / 120 * 100}%` }}>{g.s}</span>)}
      </div>
    </div>
  )
}

/** Reliability diagram: mean predicted probability vs observed rate per bin. One series, so no legend; the diagonal is labelled. */
export function ReliabilityPlot({ bins, ece }: { bins: { bin: string; n: number; mean_predicted: number; observed_rate: number }[]; ece?: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 260, H = 220, m = { l: 34, r: 10, t: 10, b: 30 }
  const x = (v: number) => m.l + v * (W - m.l - m.r)
  const y = (v: number) => H - m.b - v * (H - m.t - m.b)
  const maxN = Math.max(...bins.map(b => b.n), 1)
  const path = bins.map((b, i) => `${i ? 'L' : 'M'}${x(b.mean_predicted)},${y(b.observed_rate)}`).join(' ')
  const h = hover != null ? bins[hover] : null
  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[320px]" role="img" aria-label={`Reliability diagram${ece != null ? `, expected calibration error ${ece}` : ''}`}>
        {[0, .25, .5, .75, 1].map(t => (
          <g key={t}>
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} className="stroke-slate-200" strokeWidth={1} />
            <text x={m.l - 6} y={y(t) + 3} textAnchor="end" className="fill-slate-400 font-mono text-[9px]">{t}</text>
            <text x={x(t)} y={H - m.b + 13} textAnchor="middle" className="fill-slate-400 font-mono text-[9px]">{t}</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} className="stroke-slate-400" strokeWidth={1} strokeDasharray="4 4" />
        <text x={x(.62)} y={y(.62) - 6} className="fill-slate-500 text-[9px]" transform={`rotate(-40 ${x(.62)} ${y(.62) - 6})`}>perfect calibration</text>
        <path d={path} fill="none" stroke="#2a78d6" strokeWidth={2} strokeLinejoin="round" />
        {bins.map((b, i) => (
          <g key={b.bin} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}>
            <circle cx={x(b.mean_predicted)} cy={y(b.observed_rate)} r={14} fill="transparent" />
            <circle cx={x(b.mean_predicted)} cy={y(b.observed_rate)} r={4 + 4 * Math.sqrt(b.n / maxN)} fill="#2a78d6" className="stroke-surface" strokeWidth={2} />
          </g>
        ))}
        <text x={(x(0) + x(1)) / 2} y={H - 3} textAnchor="middle" className="fill-slate-500 text-[9px]">mean predicted probability</text>
        <text x={9} y={(y(0) + y(1)) / 2} textAnchor="middle" transform={`rotate(-90 9 ${(y(0) + y(1)) / 2})`} className="fill-slate-500 text-[9px]">observed rate</text>
      </svg>
      {h && (
        <div className="pointer-events-none absolute left-12 top-2 rounded-lg border border-slate-200 bg-surface px-2.5 py-1.5 text-[11px] shadow-lift">
          <p className="font-semibold text-slate-800">Bin {h.bin}</p>
          <p className="text-slate-600">predicted {h.mean_predicted} · observed {h.observed_rate}</p>
          <p className="text-slate-400">{h.n} holdout patients</p>
        </div>
      )}
    </figure>
  )
}
