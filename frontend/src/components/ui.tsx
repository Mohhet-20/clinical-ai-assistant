import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDot, Info, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

// ---------------------------------------------------------------- theme
const THEME_KEY = 'clarity.theme'
export function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const toggle = useCallback(() => {
    setDark(d => {
      const next = !d
      document.documentElement.classList.toggle('dark', next)
      try { localStorage.setItem(THEME_KEY, next ? 'dark' : 'light') } catch { /* storage blocked */ }
      return next
    })
  }, [])
  return { dark, toggle }
}

// ---------------------------------------------------------------- status (always icon + label, never colour alone)
export type Level = 'good' | 'warning' | 'serious' | 'critical' | 'neutral'
const LEVEL_STYLE: Record<Level, { dot: string; badge: string; Icon: typeof Info }> = {
  good: { dot: 'bg-status-good', badge: 'bg-emerald-50 text-emerald-800 ring-emerald-200', Icon: CheckCircle2 },
  warning: { dot: 'bg-status-warning', badge: 'bg-amber-50 text-amber-800 ring-amber-200', Icon: CircleDot },
  serious: { dot: 'bg-status-serious', badge: 'bg-orange-50 text-orange-800 ring-orange-200', Icon: AlertTriangle },
  critical: { dot: 'bg-status-critical', badge: 'bg-red-50 text-red-800 ring-red-200', Icon: AlertOctagon },
  neutral: { dot: 'bg-slate-400', badge: 'bg-slate-100 text-slate-600 ring-slate-200', Icon: Info },
}
export const levelDot = (l: Level) => LEVEL_STYLE[l].dot

export function StatusBadge({ level, children, className = '' }: { level: Level; children: React.ReactNode; className?: string }) {
  const { badge, Icon } = LEVEL_STYLE[level]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${badge} ${className}`}>
      <Icon className="h-3 w-3" aria-hidden />{children}
    </span>
  )
}

export const riskLevel = (r?: string): Level =>
  r === 'high' ? 'critical' : r === 'medium' ? 'serious' : r === 'moderate' || r === 'low-medium' ? 'warning' : r === 'low' ? 'good' : 'neutral'

// ---------------------------------------------------------------- layout bits
export function Panel({ title, icon, right, children, className = '' }: { title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card animate-fade-up p-4 sm:p-5 ${className}`}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">{icon}{title}</h3>
        {right && <div className="text-right">{right}</div>}
      </header>
      {children}
    </section>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; count?: number; icon?: React.ReactNode }[]; value: T; onChange: (t: T) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  function onKey(e: React.KeyboardEvent, i: number) {
    const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!dir) return
    e.preventDefault()
    const next = tabs[(i + dir + tabs.length) % tabs.length].id
    onChange(next)
    refs.current[next]?.focus()
  }
  return (
    <div role="tablist" aria-label="Result views" className="-mx-1 flex overflow-x-auto border-b border-slate-200 print:hidden">
      {tabs.map((t, i) => (
        <button key={t.id} ref={el => { refs.current[t.id] = el }} role="tab" id={`tab-${t.id}`} aria-controls={`panel-${t.id}`}
          aria-selected={value === t.id} tabIndex={value === t.id ? 0 : -1} className="tab flex items-center gap-1.5"
          onClick={() => onChange(t.id)} onKeyDown={e => onKey(e, i)}>
          {t.icon}{t.label}
          {t.count != null && t.count > 0 && <span className="rounded-full bg-slate-100 px-1.5 text-[10px] font-semibold tabular-nums text-slate-600">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- toasts
type Toast = { id: number; text: string; tone: 'ok' | 'error' }
const ToastCtx = createContext<(text: string, tone?: Toast['tone']) => void>(() => undefined)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((text: string, tone: Toast['tone'] = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t.slice(-2), { id, text, tone }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2 print:hidden">
        {toasts.map(t => (
          <div key={t.id} className={`pointer-events-auto flex max-w-sm animate-fade-up items-start gap-2 rounded-xl border bg-surface px-3.5 py-2.5 text-sm shadow-lift ${t.tone === 'error' ? 'border-red-200 text-red-800' : 'border-slate-200 text-slate-800'}`}>
            {t.tone === 'error' ? <AlertTriangle className="mt-0.5 h-4 w-4 flex-none text-status-critical" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 flex-none text-status-good" />}
            <span className="flex-1">{t.text}</span>
            <button className="text-slate-400 hover:text-slate-700" aria-label="Dismiss" onClick={() => setToasts(x => x.filter(y => y.id !== t.id))}><X className="h-3.5 w-3.5" /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

// ---------------------------------------------------------------- dialog
export function Dialog({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = ''; prev?.focus() }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm sm:p-8" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={`card w-full animate-fade-up outline-none ${wide ? 'max-w-4xl' : 'max-w-lg'}`}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5">
          <h2 className="font-semibold text-slate-900">{title}</h2>
          <button className="btn-ghost" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
