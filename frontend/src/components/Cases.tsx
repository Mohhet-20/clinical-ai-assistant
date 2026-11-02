import { useCallback, useEffect, useState } from 'react'
import { deleteCase, getCase, listCases } from '../api'
import type { CaseSummary, Result } from '../types'

/** Case worklist from the server's encrypted case store (only rendered when the store is enabled). */
export default function Cases({ refreshKey, onOpen }: { refreshKey: unknown; onOpen: (r: Result) => void }) {
  const [items, setItems] = useState<CaseSummary[]>([])
  const [retention, setRetention] = useState<number | undefined>()
  const [error, setError] = useState('')

  const load = useCallback(() => {
    listCases().then(r => { setItems(r.cases); setRetention(r.retention_days); setError('') }).catch(e => setError(e instanceof Error ? e.message : 'Could not load cases'))
  }, [])
  useEffect(load, [load, refreshKey])

  async function open(id: string) {
    try { const c = await getCase(id); if (c.result) onOpen(c.result); else setError(c.error ?? 'Case unavailable') }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not open case') }
  }
  async function remove(id: string) {
    if (!confirm('Permanently delete this case? This cannot be undone.')) return
    try { await deleteCase(id); load() } catch (e) { setError(e instanceof Error ? e.message : 'Delete failed') }
  }

  return (
    <section className="card p-5 print:hidden">
      <div className="mb-3 flex items-center justify-between"><h2 className="text-base font-semibold">Case history</h2>
        <span className="label">encrypted · {retention ? `${retention}-day retention` : 'retention policy'}</span></div>
      {error && <p role="alert" className="mb-2 text-xs text-red-600">{error}</p>}
      {items.length === 0 ? <p className="text-sm text-slate-500">No saved cases yet.</p> : (
        <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {items.map(c => (
            <li key={c.id} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs">
              {c.urgent && <span className="h-2 w-2 flex-none rounded-full bg-red-500" aria-label="Urgent" />}
              <button type="button" className="min-w-0 flex-1 text-left hover:text-brand-700" onClick={() => open(c.id)}>
                <span className="block truncate font-medium">{c.conditions[0] ?? 'No condition suggested'}{c.conditions.length > 1 && ` +${c.conditions.length - 1}`}</span>
                <span className="font-mono text-[10px] text-slate-400">{new Date(c.created * 1000).toLocaleString()} · {c.modality}{c.news2 != null && ` · NEWS2 ${c.news2}`}</span>
              </button>
              <button type="button" className="text-[11px] text-slate-400 hover:text-red-600" onClick={() => remove(c.id)} aria-label="Delete case">Delete</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
