import { FormEvent, useEffect, useRef, useState } from 'react'
import { chat } from '../api'
import type { Message } from '../types'

const INTRO: Message = { role: 'assistant', content: 'Ask a follow-up about this case; answers use retrieved evidence and source ids.' }

export default function Chat({ context }: { context: string }) {
  const [messages, setMessages] = useState<Message[]>([INTRO])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [messages])

  async function ask(e: FormEvent) {
    e.preventDefault()
    const message = q.trim()
    if (!message || busy) return
    const history = messages.filter(m => m !== INTRO)
    setQ(''); setBusy(true); setMessages(m => [...m, { role: 'user', content: message }])
    try {
      const r = await chat(message, context, history)
      setMessages(m => [...m, { role: 'assistant', content: r.reply, evidence: r.evidence }])
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', content: err instanceof Error ? err.message : 'Chat request failed' }])
    } finally { setBusy(false) }
  }

  return (
    <section className="card flex flex-col p-5">
      <div className="mb-3 flex items-center justify-between"><h2 className="text-base font-semibold">3 · Ask about this case</h2><span className="label">RAG chat</span></div>
      <div className="max-h-80 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'ml-auto bg-brand-600 text-white' : 'bg-slate-100 text-slate-800'}`}>
            <p className="whitespace-pre-line">{m.content}</p>
            {m.evidence && m.evidence.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {m.evidence.map(e => (e.url
                  ? <a key={e.id} href={e.url} target="_blank" rel="noreferrer" className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] text-brand-700 ring-1 ring-slate-200 hover:underline">{e.id}</a>
                  : <span key={e.id} className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-500 ring-1 ring-slate-200">{e.id}</span>))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="text-xs text-slate-400">Retrieving evidence…</div>}
        <div ref={end} />
      </div>
      <form onSubmit={ask} className="mt-3 flex gap-2">
        <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="e.g. What confirms a diabetes diagnosis?" aria-label="Question" />
        <button className="btn-primary px-4" disabled={busy || !q.trim()} aria-label="Send">↑</button>
      </form>
      <p className="mt-2 text-[11px] text-slate-500">Answers need clinician verification.</p>
    </section>
  )
}
