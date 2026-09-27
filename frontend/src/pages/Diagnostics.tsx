import { useTranslation } from 'react-i18next'
import { usePolling } from '../usePolling'
import styles from './Diagnostics.module.css'

type Diagnostics = {
  process: { cpu_percent: number | null; memory_mb: number; threads: number; cpus: number | null; load: number[] }
  cameras: { id: string; state: string; fps: number; frames: number; dropped: number; last_error: string | null }[]
  detection: { state: string; available: boolean; model: string | null; step_ms: number; darts_in_turn: number }
  recent_darts: {
    label: string
    live_label: string | null
    confidence: number
    accepted: boolean
    time: string
    cameras: string[]
  }[]
}

/** Load, cameras and detection at a glance (instead of logging in via SSH). */
export default function DiagnosticsPage() {
  const { t, i18n } = useTranslation()
  const data = usePolling<Diagnostics>('/api/diagnostics', 2000)
  if (data.kind === 'loading') return <p className="muted">{t('cameras.loading')}</p>
  if (data.kind === 'error') return <p className="error">{data.message}</p>
  const d = data.data
  const cores = d.process.cpus ?? 1
  const cpu = d.process.cpu_percent
  return (
    <>
      <h1 className={styles.title}>{t('diagnostics.title')}</h1>
      <div className={styles.tiles}>
        <Tile
          label={t('diagnostics.cpu', { cores })}
          value={cpu === null ? '–' : `${Math.round(cpu)} %`}
          warn={cpu !== null && cpu > 150}
        />
        <Tile label={t('diagnostics.memory')} value={`${Math.round(d.process.memory_mb)} MB`} />
        <Tile label={t('diagnostics.load')} value={d.process.load.length ? d.process.load.join(' · ') : '–'} />
        <Tile label={t('diagnostics.step')} value={`${d.detection.step_ms.toFixed(1)} ms`} warn={d.detection.step_ms > 50} />
        <Tile label={t('diagnostics.state')} value={t(`detection.state.${d.detection.state}` as 'detection.state.idle', { defaultValue: d.detection.state })} />
      </div>

      <section className="card">
        <h2 className="cardTitle">{t('nav.cameras')}</h2>
        <table className={styles.table}>
          <thead>
            <tr>
              <th />
              <th>{t('diagnostics.cameraState')}</th>
              <th>FPS</th>
              <th>{t('diagnostics.frames')}</th>
              <th>{t('diagnostics.dropped')}</th>
            </tr>
          </thead>
          <tbody>
            {d.cameras.map((c) => (
              <tr key={c.id}>
                <th scope="row">{c.id}</th>
                <td className={c.state === 'running' ? styles.ok : styles.bad}>{c.state}</td>
                <td className={c.fps < 20 ? styles.bad : undefined}>{c.fps.toFixed(1)}</td>
                <td>{c.frames}</td>
                <td>{c.dropped}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.cameras.some((c) => c.last_error) && (
          <p className="error">{d.cameras.map((c) => c.last_error && `${c.id}: ${c.last_error}`).filter(Boolean).join(' · ')}</p>
        )}
      </section>

      <section className="card">
        <h2 className="cardTitle">{t('diagnostics.recent')}</h2>
        {d.recent_darts.length === 0 ? (
          <p className="muted">{t('diagnostics.noDarts')}</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t('diagnostics.time')}</th>
                <th>{t('diagnostics.dart')}</th>
                <th>{t('diagnostics.confidence')}</th>
                <th>{t('diagnostics.usedCameras')}</th>
              </tr>
            </thead>
            <tbody>
              {d.recent_darts.map((dart, i) => (
                <tr key={i} className={dart.accepted ? undefined : styles.muted}>
                  <td>{new Date(dart.time).toLocaleTimeString(i18n.language)}</td>
                  <td>
                    <strong>{dart.label}</strong>
                    {dart.live_label && <span className={styles.second}> {t('diagnostics.secondLook', { label: dart.live_label })}</span>}
                  </td>
                  <td className={dart.confidence < 0.5 ? styles.bad : undefined}>{Math.round(dart.confidence * 100)} %</td>
                  <td>{dart.cameras.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted">{t('diagnostics.hint')}</p>
      </section>
    </>
  )
}

function Tile({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`card ${styles.tile} ${warn ? styles.warn : ''}`}>
      <span className={styles.value}>{value}</span>
      <span className="muted">{label}</span>
    </div>
  )
}
