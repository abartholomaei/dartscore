import type { Health } from '../api'
import { usePolling } from '../usePolling'
import styles from './Home.module.css'

export default function Home() {
  const health = usePolling<Health>('/api/health', 5000)

  return (
    <>
      <h1 className={styles.title}>dartscore</h1>
      <section className="card" aria-live="polite">
        <h2 className="cardTitle">Backend</h2>
        {health.kind === 'loading' && <p className="muted">Verbinde …</p>}
        {health.kind === 'error' && <p className="error">Nicht erreichbar ({health.message})</p>}
        {health.kind === 'ok' && (
          <dl className={styles.stats}>
            <dt>Status</dt>
            <dd className="ok">{health.data.status}</dd>
            <dt>Version</dt>
            <dd>{health.data.version}</dd>
            <dt>Kameras</dt>
            <dd>{health.data.cameras_configured}</dd>
          </dl>
        )}
      </section>
    </>
  )
}
