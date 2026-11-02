import { Activity, ArrowRight, FileText, HeartPulse, ImageIcon, Loader2, Stethoscope, Syringe, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { DIABETES_FIELDS, HEART_FIELDS, SAMPLES, type Sample } from '../samples'

type Props = {
  text: string; setText: (v: string) => void; file: File | null; setFile: (f: File | null) => void
  features: Record<string, string>; setFeatures: (f: Record<string, string>) => void
  busy: boolean; error: string; onSubmit: () => void; onSample: (s: Sample) => void; activeSample: string | null
}
const SAMPLE_ICON: Record<string, typeof Activity> = { sepsis: Activity, 'ed-shorthand': Stethoscope, diabetes: Syringe, cardiac: HeartPulse }

function FieldGrid({ title, fields, values, onChange }: { title: string; fields: { key: string; hint: string }[]; values: Record<string, string>; onChange: (k: string, v: string) => void }) {
  return (
    <div>
      <p className="label mb-2">{title}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {fields.map(f => (
          <label key={f.key} className="grid gap-1 text-[11px] font-medium text-slate-600">
            {f.key}
            <input className="input" type="number" step="any" placeholder={f.hint} title={f.hint} value={values[f.key] ?? ''} onChange={e => onChange(f.key, e.target.value)} />
          </label>
        ))}
      </div>
    </div>
  )
}

export default function Intake({ text, setText, file, setFile, features, setFeatures, busy, error, onSubmit, onSample, activeSample }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const set = (k: string, v: string) => setFeatures({ ...features, [k]: v })
  const canSubmit = !busy && (!!text.trim() || !!file)
  const mod = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl'

  return (
    <section id="intake" className="card p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">Patient record</h2>
        <span className="label">text · PDF · image</span>
      </div>

      <p className="label mb-2">One-click sample cases</p>
      <div className="grid grid-cols-2 gap-2">
        {SAMPLES.map(s => {
          const Icon = SAMPLE_ICON[s.id] ?? FileText
          const active = activeSample === s.id
          return (
            <button key={s.id} type="button" data-sample={s.id} disabled={busy} onClick={() => onSample(s)}
              className={`group rounded-xl border p-3 text-left transition hover:-translate-y-0.5 hover:border-brand-500 hover:shadow-card disabled:opacity-60 ${active ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-slate-200 bg-surface'}`}>
              <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-900"><Icon className="h-3.5 w-3.5 text-brand-600" />{s.name}</span>
              <span className="mt-0.5 block text-[11px] leading-snug text-slate-500">{s.blurb}</span>
            </button>
          )
        })}
      </div>

      <div className="my-4 flex items-center gap-3 text-[11px] text-slate-400"><span className="h-px flex-1 bg-slate-200" />or your own de-identified note<span className="h-px flex-1 bg-slate-200" /></div>

      <label htmlFor="notes" className="sr-only">Symptoms, history and findings</label>
      <textarea
        id="notes" rows={6} value={text} onChange={e => setText(e.target.value)} maxLength={30000}
        onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canSubmit) { e.preventDefault(); onSubmit() } }}
        placeholder="e.g. 58-year-old with thirst and frequent urination. On metformin 500 mg BD. BP 150/92, HR 96, SpO2 97% RA, fasting glucose 164 mg/dL…"
        className="input min-h-[132px] resize-y leading-relaxed"
      />

      <div
        role="button" tabIndex={0} aria-label="Attach a report or image"
        onClick={() => input.current?.click()} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click() } }}
        onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); setFile(e.dataTransfer.files[0] ?? null) }}
        className={`mt-2 flex cursor-pointer items-center gap-3 rounded-xl border border-dashed px-3 py-2.5 text-xs transition ${drag ? 'border-brand-500 bg-brand-50' : 'border-slate-300 hover:border-brand-500'}`}
      >
        <Upload className="h-4 w-4 text-slate-400" />
        <span className="text-slate-600"><b className="text-slate-800">Attach</b> a PDF, TXT or image (X-ray, ECG, lab scan) · max 12 MB</span>
        <input ref={input} className="hidden" type="file" accept="application/pdf,text/plain,.txt,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} />
      </div>
      {file && (
        <div className="mt-2 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
          <span className="flex min-w-0 items-center gap-2 truncate">{file.type.startsWith('image/') ? <ImageIcon className="h-4 w-4 text-slate-400" /> : <FileText className="h-4 w-4 text-slate-400" />}{file.name}
            <span className="text-slate-400">({Math.max(1, Math.round(file.size / 1024))} KB)</span></span>
          <button className="btn-ghost" onClick={() => setFile(null)} aria-label="Remove file"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">Structured model inputs <span className="font-normal text-slate-400">(optional; vitals in the note are read automatically)</span></summary>
        <div className="mt-3 grid gap-4">
          <FieldGrid title="Diabetes model (Pima) · needs Glucose, BMI, Age" fields={DIABETES_FIELDS} values={features} onChange={set} />
          <FieldGrid title="Heart-disease model (UCI Cleveland) · needs all 13 fields" fields={HEART_FIELDS} values={features} onChange={set} />
        </div>
      </details>

      <button className="btn-primary mt-4 w-full py-3" disabled={!canSubmit} onClick={onSubmit}>
        {busy ? <><Loader2 className="h-4 w-4 animate-spin" />Analysing…</> : <>Analyse record <ArrowRight className="h-4 w-4" /><span className="ml-1 hidden rounded bg-black/20 px-1.5 font-mono text-[10px] sm:inline">{mod} ↵</span></>}
      </button>
      {error && <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">Use synthetic or de-identified data. Identifiers are pattern-redacted before external calls, but redaction cannot be guaranteed complete.</p>
    </section>
  )
}
