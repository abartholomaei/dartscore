import { useTranslation } from 'react-i18next'
import { sendJson, type DetectionStatus } from '../api'
import { useLiveGame } from '../LiveGame'
import styles from './DetectionBadge.module.css'

/** Shows whether automatic detection is listening, and toggles it. */
export default function DetectionBadge() {
  const { t } = useTranslation()
  const { detection, setDetection } = useLiveGame()
  if (!detection) return null

  const toggle = async () => {
    setDetection(await sendJson<DetectionStatus>('PUT', '/api/detection', { enabled: !detection.enabled }))
  }

  const state = !detection.available ? 'unavailable' : !detection.enabled ? 'off' : detection.state
  return (
    <button
      className={`${styles.badge} ${styles[state]}`}
      onClick={() => void toggle()}
      disabled={!detection.available}
      title={t(`detection.hint.${state}`)}
    >
      <span className={styles.dot} aria-hidden="true" />
      {t(`detection.state.${state}`)}
    </button>
  )
}
