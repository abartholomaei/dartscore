import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { Health } from '../api'
import { LANGUAGES } from '../i18n'
import { usePolling } from '../usePolling'
import styles from './Settings.module.css'

export default function Settings() {
  const { t, i18n } = useTranslation()
  const health = usePolling<Health>('/api/health', 10000)

  return (
    <>
      <h1 className={styles.title}>{t('settings.title')}</h1>
      <div className={styles.grid}>
        <Link to="/cameras" className={`card ${styles.link}`}>
          <strong>{t('nav.cameras')}</strong>
          <span className="muted">{t('settings.camerasHint')}</span>
        </Link>
        <Link to="/calibration" className={`card ${styles.link}`}>
          <strong>{t('nav.calibration')}</strong>
          <span className="muted">{t('settings.calibrationHint')}</span>
        </Link>
        <section className={`card ${styles.link}`}>
          <strong>{t('language.label')}</strong>
          <div className={styles.languages}>
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                className={i18n.resolvedLanguage === lang.code ? 'button primary' : 'button'}
                onClick={() => void i18n.changeLanguage(lang.code)}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </section>
        <section className={`card ${styles.link}`}>
          <strong>{t('settings.system')}</strong>
          {health.kind === 'ok' ? (
            <span className="muted">
              {t('home.version')} {health.data.version} · {t('home.cameras')}: {health.data.cameras_configured}
            </span>
          ) : health.kind === 'error' ? (
            <span className="error">{t('home.unreachable', { message: health.message })}</span>
          ) : (
            <span className="muted">{t('home.connecting')}</span>
          )}
        </section>
      </div>
    </>
  )
}
