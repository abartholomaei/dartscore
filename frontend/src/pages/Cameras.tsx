import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getOptional, streamUrl, type Calibration, type CameraStatus } from '../api'
import BoardOverlay from '../components/BoardOverlay'
import { usePolling } from '../usePolling'
import styles from './Cameras.module.css'

export default function Cameras() {
  const { t } = useTranslation()
  const cameras = usePolling<CameraStatus[]>('/api/cameras', 2000)
  const [undistort, setUndistort] = useState(false)
  const [showOverlay, setShowOverlay] = useState(false)

  const anyCalibrated = cameras.kind === 'ok' && cameras.data.some((c) => c.lens_calibrated)
  const anyBoardCalibrated = cameras.kind === 'ok' && cameras.data.some((c) => c.board_calibrated)

  return (
    <>
      <div className={styles.toolbar}>
        <h1 className={styles.title}>{t('cameras.title')}</h1>
        <label className={styles.toggle} title={anyCalibrated ? '' : t('cameras.noLensCalibration')}>
          <input
            type="checkbox"
            checked={undistort}
            disabled={!anyCalibrated}
            onChange={(e) => setUndistort(e.target.checked)}
          />
          {t('cameras.undistort')}
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={showOverlay}
            disabled={!anyBoardCalibrated}
            onChange={(e) => setShowOverlay(e.target.checked)}
          />
          {t('cameras.overlay')}
        </label>
      </div>

      {cameras.kind === 'loading' && <p className="muted">{t('cameras.loading')}</p>}
      {cameras.kind === 'error' && (
        <p className="error">{t('cameras.backendUnreachable', { message: cameras.message })}</p>
      )}
      {cameras.kind === 'ok' && cameras.data.length === 0 && (
        <p className="muted">{t('cameras.noneConfigured')}</p>
      )}
      {cameras.kind === 'ok' && (
        <div className={styles.grid}>
          {cameras.data.map((cam) => (
            <CameraCard
              key={cam.id}
              camera={cam}
              undistort={undistort && cam.lens_calibrated}
              showOverlay={showOverlay && cam.board_calibrated}
            />
          ))}
        </div>
      )}
    </>
  )
}

type CardProps = { camera: CameraStatus; undistort: boolean; showOverlay: boolean }

function CameraCard({ camera, undistort, showOverlay }: CardProps) {
  const { t } = useTranslation()
  const calibration = useCalibration(camera.id, showOverlay)
  // the overlay refers to the image space it was calibrated in
  const streamUndistorted = showOverlay && calibration ? calibration.undistorted : undistort
  const running = camera.state === 'running'
  const info = camera.info
  const stateLabel = t(`cameraState.${camera.state}`)

  return (
    <article className={`card ${styles.camera}`}>
      <div className={styles.imageBox}>
        {running ? (
          <img
            className={styles.image}
            src={streamUrl(camera.id, { width: 640, undistort: streamUndistorted })}
            alt={t('cameras.liveImage', { id: camera.id })}
          />
        ) : (
          <span className="muted">{stateLabel} …</span>
        )}
        {running && showOverlay && calibration && (
          <BoardOverlay
            overlay={calibration.overlay}
            width={calibration.image_size[0]}
            height={calibration.image_size[1]}
            showLabels={false}
          />
        )}
      </div>
      <header className={styles.cameraHeader}>
        <h2 className={styles.cameraTitle}>{camera.id}</h2>
        <span className={`${styles.badge} ${styles[camera.state]}`}>{stateLabel}</span>
      </header>
      <dl className={styles.meta}>
        <dt>{t('cameras.frameRate')}</dt>
        <dd>{t('cameras.fps', { value: camera.fps })}</dd>
        <dt>{t('cameras.format')}</dt>
        <dd>{info ? `${info.width}×${info.height} ${info.fourcc}` : '–'}</dd>
        <dt>{t('cameras.position')}</dt>
        <dd>{camera.position_deg}°</dd>
        <dt>{t('cameras.dropped')}</dt>
        <dd>{t('cameras.droppedFrames', { count: camera.dropped })}</dd>
        <dt>{t('cameras.lens')}</dt>
        <dd>{camera.lens_calibrated ? t('cameras.lensCalibrated') : t('cameras.lensNotCalibrated')}</dd>
        <dt>{t('cameras.source')}</dt>
        <dd className={styles.device}>
          {camera.source === 'synthetic' ? t('cameras.simulation') : camera.device}
        </dd>
      </dl>
      {camera.last_error && <p className={`error ${styles.errorText}`}>{camera.last_error}</p>}
    </article>
  )
}

/** Loads the board calibration of a camera while `enabled`. */
function useCalibration(cameraId: string, enabled: boolean): Calibration | null {
  const [calibration, setCalibration] = useState<Calibration | null>(null)
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    getOptional<Calibration>(`/api/cameras/${cameraId}/calibration`, controller.signal)
      .then(setCalibration)
      .catch(() => undefined)
    return () => controller.abort()
  }, [cameraId, enabled])
  return enabled ? calibration : null
}
