import { FlaskConical } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getModels } from '../api'
import type { ModelCard } from '../types'
import { ReliabilityPlot } from './Charts'
import { Dialog, StatusBadge } from './ui'

const METRICS: [string, string][] = [['holdout_roc_auc', 'Holdout AUC'], ['cv_roc_auc_mean', '5-fold CV AUC'], ['holdout_sensitivity', 'Sensitivity @0.5'],
  ['holdout_specificity', 'Specificity @0.5'], ['holdout_brier', 'Brier score'], ['holdout_ece', 'Calibration error (ECE)']]

/** Model cards: intended use, population, limitations, metrics and calibration, straight from /v1/models. */
export default function Models({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [cards, setCards] = useState<Record<string, ModelCard> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (open && !cards) getModels().then(setCards).catch(e => setError(e instanceof Error ? e.message : 'Model cards unavailable'))
  }, [open, cards])

  return (
    <Dialog open={open} onClose={onClose} title="Model cards" wide>
      <p className="mb-4 text-sm text-slate-600">Both risk models are small logistic regressions on historical research cohorts. They are shown as <b>signals</b>, not personal risks. The calibration plots show why: the diabetes model over-predicts at the high end.</p>
      {error && <p role="alert" className="text-sm text-red-700">{error} Model cards need the live API.</p>}
      {!cards && !error && <div className="space-y-3"><div className="skeleton h-40" /><div className="skeleton h-40" /></div>}
      <div className="space-y-5">
        {cards && Object.entries(cards).map(([key, m]) => (
          <article key={key} className="rounded-2xl border border-slate-200 p-4">
            <header className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 font-semibold text-slate-900"><FlaskConical className="h-4 w-4 text-brand-600" />{m.label}</h3>
              <span className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-slate-500">{m.version}</span>
                <StatusBadge level={m.available ? 'good' : 'critical'}>{m.available ? 'Loaded · integrity verified' : 'Unavailable'}</StatusBadge>
              </span>
            </header>
            <p className="mt-1 text-xs text-slate-500">{m.model} · target: {m.target}</p>
            <div className="mt-4 grid gap-5 md:grid-cols-[1fr_300px]">
              <div className="space-y-3 text-sm">
                <p><span className="label block">Intended use</span>{m.card.intended_use}</p>
                <p><span className="label block">Population</span>{m.card.population}</p>
                <div><span className="label block">Out of scope</span><ul className="list-disc pl-5 text-slate-700">{m.card.out_of_scope.map(x => <li key={x}>{x}</li>)}</ul></div>
                <div><span className="label block">Limitations</span><ul className="list-disc pl-5 text-slate-700">{m.card.limitations.map(x => <li key={x}>{x}</li>)}</ul></div>
                {m.metrics && (
                  <table className="w-full text-xs">
                    <caption className="label pb-1 text-left">Holdout metrics (n={m.metrics.holdout_rows ?? '–'}) · trained on {m.metrics.rows} rows</caption>
                    <tbody>{METRICS.map(([k, label]) => (
                      <tr key={k} className="border-t border-slate-100"><td className="py-1 text-slate-600">{label}</td>
                        <td className="text-right font-mono tabular-nums text-slate-900">{(m.metrics as Record<string, unknown>)[k] as number ?? '–'}</td></tr>))}</tbody>
                  </table>
                )}
                <p className="break-all font-mono text-[10px] text-slate-400">training data sha256 {m.data_sha256}</p>
              </div>
              {m.metrics?.calibration_table && (
                <div>
                  <p className="label mb-1">Calibration on holdout</p>
                  <ReliabilityPlot bins={m.metrics.calibration_table} ece={m.metrics.holdout_ece} />
                  <p className="mt-1 text-[11px] text-slate-500">Points below the diagonal: the model predicts more risk than was observed. Dot size is the number of patients in the bin.</p>
                </div>
              )}
            </div>
          </article>
        ))}
      </div>
    </Dialog>
  )
}
