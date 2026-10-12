import { useRef, useState } from 'react'
import { DIABETES_FIELDS, HEART_FIELDS, SAMPLES } from '../samples'

type Props = {
  text: string; setText: (v: string) => void; file: File | null; setFile: (f: File | null) => void
  features: Record<string, string>; setFeatures: (f: Record<string, string>) => void
  busy: boolean; error: string; onSubmit: () => void
}

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

export default function Intake({ text, setText, file, setFile, features, setFeatures, busy, error, onSubmit }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const set = (k: string, v: string) => setFeatures({ ...features, [k]: v })
  const isImage = file?.type.startsWith('image/')

  return (
    <section className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold">1 · Patient information</h2>
        <span className="label">multimodal input</span>
      </div>

      <div
        role="button" tabIndex={0} aria-label="Upload a report"
        onClick={() => input.current?.click()} onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click() }
        }}
        onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); setFile(e.dataTransfer.files[0] ?? null) }}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 border-dashed px-4 py-6 text-center transition ${drag ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:border-brand-500 hover:bg-brand-50/50'}`}
      >
        <span className="text-2xl text-brand-600">⇪</span>
        <strong className="text-sm">Drop a clinical report or image, or <u>browse</u></strong>
        <small className="text-xs text-slate-500">PDF, TXT (reports) · PNG, JPEG, WebP (X-ray / fundus / ECG) · max 12 MB</small>
        <input ref={input} className="hidden" type="file" accept="application/pdf,text/plain,.txt,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} />
      </div>
      {file && (
        <div className="mt-2 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
          <span className="truncate">{isImage ? '🖼' : '📄'} {file.name} <span className="text-slate-400">({Math.max(1, Math.round(file.size / 1024))} KB)</span></span>
          <button className="ml-3 text-xs font-medium text-slate-500 hover:text-red-600" onClick={() => setFile(null)}>Remove</button>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="label">Try a sample</span>
        {SAMPLES.map(s => (
          <button key={s.name} className="chip transition hover:bg-brand-100" onClick={() => { setText(s.text); setFeatures(s.features); setFile(null) }}>{s.name}</button>
        ))}
      </div>

      <label htmlFor="notes" className="label mb-1.5 mt-4 block">Symptoms, history & findings</label>
      <textarea
        id="notes" rows={7} value={text} onChange={e => setText(e.target.value)} maxLength={30000}
        placeholder="e.g. 58-year-old with increased thirst and frequent urination. Taking metformin. BP 150/92, fasting glucose 164 mg/dL, BMI 31…"
        className="input min-h-[140px] resize-y leading-relaxed"
      />

      <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">Structured model inputs <span className="font-normal text-slate-400">(optional — vitals in the note are picked up automatically)</span></summary>
        <div className="mt-3 grid gap-4">
          <FieldGrid title="Diabetes model (Pima) · needs Glucose, BMI, Age" fields={DIABETES_FIELDS} values={features} onChange={set} />
          <FieldGrid title="Heart-disease model (UCI Cleveland) · needs all 13 fields" fields={HEART_FIELDS} values={features} onChange={set} />
        </div>
      </details>

      <button className="btn-primary mt-4 w-full" disabled={busy || (!text.trim() && !file)} onClick={onSubmit}>
        {busy ? 'Agent is working…' : 'Analyze patient →'}
      </button>
      {error && <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">Prototype only. Do not enter identifiable patient information.</p>
    </section>
  )
}
