import { Loader2, MessagesSquare, SendHorizontal } from 'lucide-react'
import { FormEvent, useEffect, useRef, useState } from 'react'
import { chat } from '../api'
import type { Message } from '../types'

const INTRO: Message = { role: 'assistant', content: 'Ask a follow-up about this case. Answers come only from retrieved evidence and cite source ids.' }
const SUGGESTIONS = ['What confirms a diabetes diagnosis?', 'When does NEWS2 need an emergency response?', 'What are qSOFA criteria?']

export default function Chat({ context }: { context: string }) {
  const [messages, setMessages] = useState<Message[]>([INTRO])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const list = useRef<HTMLDivElement>(null)
  // Scroll the message list itself, never the window (scrollIntoView on mount used to jump the whole page here).
  useEffect(() => { if (messages.length > 1 && list.current) list.current.scrollTop = list.current.scrollHeight }, [messages, busy])

  async function ask(e: FormEvent | null, text = q) {
    e?.preventDefault()
    const message = text.trim()
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
    <section className="card flex flex-col p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900"><MessagesSquare className="h-4 w-4 text-brand-600" />Ask about this case</h2>
        <span className="label">evidence-grounded</span>
      </div>
      <div ref={list} className="max-h-80 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[92%] animate-fade-up rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'ml-auto rounded-br-md bg-action text-white' : 'rounded-bl-md bg-slate-100 text-slate-800'}`}>
            <p className="whitespace-pre-line">{m.content}</p>
            {!!m.evidence?.length && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {m.evidence.map(e => (e.url
                  ? <a key={e.id} href={e.url} target="_blank" rel="noreferrer" className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-brand-700 ring-1 ring-slate-200 hover:underline">{e.id}</a>
                  : <span key={e.id} className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-slate-500 ring-1 ring-slate-200">{e.id}</span>))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="flex items-center gap-1.5 text-xs text-slate-400"><Loader2 className="h-3 w-3 animate-spin" />Retrieving evidence…</div>}
      </div>
      {messages.length === 1 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map(s => <button key={s} type="button" className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] text-slate-600 transition hover:border-brand-500 hover:text-brand-700" onClick={() => ask(null, s)}>{s}</button>)}
        </div>
      )}
      <form onSubmit={ask} className="mt-3 flex gap-2">
        <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="Ask a question…" aria-label="Question" />
        <button className="btn-primary px-3" disabled={busy || !q.trim()} aria-label="Send"><SendHorizontal className="h-4 w-4" /></button>
      </form>
      <p className="mt-2 text-[11px] text-slate-500">Answers need clinician verification.</p>
    </section>
  )
}
