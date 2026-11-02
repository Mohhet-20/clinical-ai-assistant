import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import Consent from './components/Consent'
import { ToastProvider } from './components/ui'
import './style.css'

/** A rendering fault must never leave a clinician staring at a blank page or a half-drawn result. */
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div role="alert" className="mx-auto mt-24 max-w-md rounded-2xl border border-red-200 bg-surface p-6 text-center shadow-sm">
        <h1 className="text-lg font-semibold">Something went wrong displaying this page.</h1>
        <p className="mt-2 text-sm text-slate-600">No result is shown rather than a possibly incomplete one. Reload to start again.</p>
        <button className="btn-primary mt-4" onClick={() => location.reload()}>Reload</button>
      </div>
    )
  }
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><ToastProvider><Consent><App /></Consent></ToastProvider></ErrorBoundary></React.StrictMode>)
