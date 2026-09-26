import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getJson, sendJson, streamUrl, type CameraStatus, type Point } from '../api'
import { useErrorText } from '../helpers'
import styles from './LensCalibration.module.css'

type LensStatus = {
  calibrated: boolean
  rms_error: number | null
  created_at: string | null
  captures: number
  recommended: number
  minimum: number
  coverage: number
  pattern: [number, number]
}
type CaptureResult = LensStatus & { found: boolean; accepted: boolean; corners: Point[]; image_size: [number, number] }

const CAPTURE_INTERVAL_MS = 700

/** Lens calibration: the player holds the printed chessboard in front of the camera while the
 *  page keeps capturing; views that add something new are kept. */
export default function LensCalibration({ camera, onChanged }: { camera: CameraStatus; onChanged: () => void }) {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const [status, setStatus] = useState<LensStatus | null>(null)
  const [last, setLast] = useState<CaptureResult | null>(null)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState(0)
  const base = `/api/cameras/${encodeURIComponent(camera.id)}/lens`
  const runningRef = useRef(false)

  useEffect(() => {
    void getJson<LensStatus>(base).then(setStatus)
    return () => {
      runningRef.current = false
    }
  }, [base])

  // capture loop: one request at a time, so a slow chessboard search never piles up
  useEffect(() => {
    runningRef.current = running
    if (!running) return
    let timer = 0
    const tick = async () => {
      try {
        const result = await sendJson<CaptureResult>('POST', `${base}/capture`)
        setLast(result)
        setStatus(result)
        if (result.accepted) setFlash((f) => f + 1)
      } catch (err) {
        setError(errorText(err))
        setRunning(false)
        return
      }
      if (runningRef.current) timer = window.setTimeout(() => void tick(), CAPTURE_INTERVAL_MS)
    }
    void tick()
    return () => window.clearTimeout(timer)
  }, [running, base, errorText])

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await fn()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const compute = () =>
    act(async () => {
      setRunning(false)
      const result = await sendJson<LensStatus & { board_converted: boolean }>('POST', `${base}/compute`)
      setStatus(result)
      setLast(null)
      setMessage(
        t('lens.computed', { rms: result.rms_error?.toFixed(2) }) +
          (result.board_converted ? ` ${t('lens.boardConverted')}` : ''),
      )
      onChanged()
    })

  const reset = () =>
    act(async () => {
      setStatus(await sendJson<LensStatus>('DELETE', `${base}/captures`))
      setLast(null)
    })

  const remove = () =>
    act(async () => {
      if (!window.confirm(t('lens.confirmRemove'))) return
      setStatus(await sendJson<LensStatus>('DELETE', base))
      setMessage(t('lens.removed'))
      onChanged()
    })

  if (!status) return <p className="muted">{t('cameras.loading')}</p>
  const progress = Math.min(1, status.captures / status.recommended)
  const quality =
    status.rms_error === null ? null : status.rms_error < 0.5 ? 'good' : status.rms_error < 1 ? 'ok' : 'bad'

  return (
    <div className={styles.layout}>
      <section className={styles.imageColumn}>
        <div className={styles.imageBox}>
          <img src={streamUrl(camera.id, { width: 960 })} alt={camera.id} className={styles.image} />
          {last && last.corners.length > 0 && (
            <svg
              className={styles.overlay}
              viewBox={`0 0 ${last.image_size[0]} ${last.image_size[1]}`}
              preserveAspectRatio="none"
            >
              {last.corners.map(([x, y], i) => (
                <circle key={i} cx={x} cy={y} r={last.image_size[0] / 160} className={last.accepted ? styles.cornerNew : styles.corner} />
              ))}
            </svg>
          )}
          {flash > 0 && <div key={flash} className={styles.flash} aria-hidden />}
        </div>
        <div className={styles.progress} aria-label={t('lens.captures')}>
          <span style={{ width: `${progress * 100}%` }} />
        </div>
        <p className={styles.counts}>
          {t('lens.captureCount', { count: status.captures, recommended: status.recommended })} ·{' '}
          {t('lens.coverage', { value: Math.round(status.coverage * 100) })}
          {running && last && (
            <span className={last.found ? styles.found : 'muted'}>
              {' '}
              · {last.accepted ? t('lens.kept') : last.found ? t('lens.moveOn') : t('lens.searching')}
            </span>
          )}
        </p>
        <div className={styles.actions}>
          <button className={running ? 'button' : 'button primary'} onClick={() => setRunning((r) => !r)} disabled={busy}>
            {running ? t('lens.stop') : t('lens.start')}
          </button>
          <button className="button" onClick={() => void reset()} disabled={busy || status.captures === 0}>
            {t('lens.reset')}
          </button>
          <button className="button primary" onClick={() => void compute()} disabled={busy || status.captures < status.minimum}>
            {t('lens.compute')}
          </button>
        </div>
        {message && <p className={styles.message}>{message}</p>}
        {error && <p className="error">{error}</p>}
      </section>

      <section className={`card ${styles.side}`}>
        <h2 className="cardTitle">{t('lens.title')}</h2>
        {status.calibrated ? (
          <p>
            <span className={quality ? styles[quality] : undefined}>{t('lens.calibratedRms', { rms: status.rms_error?.toFixed(2) })}</span>
            <br />
            <span className="muted">{status.created_at && new Date(status.created_at).toLocaleString()}</span>
          </p>
        ) : (
          <p className="muted">{t('lens.notCalibrated')}</p>
        )}
        <ol className={styles.steps}>
          <li>
            {t('lens.step1')}{' '}
            <a href="/chessboard.svg" target="_blank" rel="noreferrer">
              {t('lens.printLink')}
            </a>
          </li>
          <li>{t('lens.step2')}</li>
          <li>{t('lens.step3')}</li>
          <li>{t('lens.step4')}</li>
        </ol>
        <p className="muted">{t('lens.hint')}</p>
        {status.calibrated && (
          <button className="button danger" onClick={() => void remove()} disabled={busy}>
            {t('lens.remove')}
          </button>
        )}
      </section>
    </div>
  )
}
