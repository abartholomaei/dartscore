import { useTranslation } from 'react-i18next'
import type { Health } from '../api'
import { usePolling } from '../usePolling'
import styles from './Home.module.css'

export default function Home() {
  const { t } = useTranslation()
  const health = usePolling<Health>('/api/health', 5000)

  return (
    <>
      <h1 className={styles.title}>dartscore</h1>
      <section className="card" aria-live="polite">
        <h2 className="cardTitle">{t('home.backend')}</h2>
        {health.kind === 'loading' && <p className="muted">{t('home.connecting')}</p>}
        {health.kind === 'error' && (
          <p className="error">{t('home.unreachable', { message: health.message })}</p>
        )}
        {health.kind === 'ok' && (
          <dl className={styles.stats}>
            <dt>{t('home.status')}</dt>
            <dd className="ok">{health.data.status}</dd>
            <dt>{t('home.version')}</dt>
            <dd>{health.data.version}</dd>
            <dt>{t('home.cameras')}</dt>
            <dd>{health.data.cameras_configured}</dd>
          </dl>
        )}
      </section>
    </>
  )
}
