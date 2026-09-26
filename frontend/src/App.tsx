import { useEffect, useState } from 'react'
import styles from './App.module.css'

type Health = {
  status: string
  version: string
  cameras_configured: number
}

type State = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

export default function App() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/health', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<Health>
      })
      .then((health) => setState({ kind: 'ok', health }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
      })
    return () => controller.abort()
  }, [])

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>dartscore</h1>
      <section className={styles.card} aria-live="polite">
        <h2 className={styles.cardTitle}>Backend</h2>
        {state.kind === 'loading' && <p className={styles.muted}>Verbinde …</p>}
        {state.kind === 'error' && (
          <p className={styles.error}>Nicht erreichbar ({state.message})</p>
        )}
        {state.kind === 'ok' && (
          <dl className={styles.stats}>
            <dt>Status</dt>
            <dd className={styles.ok}>{state.health.status}</dd>
            <dt>Version</dt>
            <dd>{state.health.version}</dd>
            <dt>Kameras</dt>
            <dd>{state.health.cameras_configured}</dd>
          </dl>
        )}
      </section>
    </main>
  )
}
