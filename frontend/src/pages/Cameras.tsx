import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { streamUrl, type CameraStatus } from '../api'
import { usePolling } from '../usePolling'
import styles from './Cameras.module.css'

export default function Cameras() {
  const { t } = useTranslation()
  const cameras = usePolling<CameraStatus[]>('/api/cameras', 2000)
  const [undistort, setUndistort] = useState(false)

  const anyCalibrated = cameras.kind === 'ok' && cameras.data.some((c) => c.lens_calibrated)

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
            <CameraCard key={cam.id} camera={cam} undistort={undistort && cam.lens_calibrated} />
          ))}
        </div>
      )}
    </>
  )
}

function CameraCard({ camera, undistort }: { camera: CameraStatus; undistort: boolean }) {
  const { t } = useTranslation()
  const running = camera.state === 'running'
  const info = camera.info
  const stateLabel = t(`cameraState.${camera.state}`)

  return (
    <article className={`card ${styles.camera}`}>
      <div className={styles.imageBox}>
        {running ? (
          <img
            className={styles.image}
            src={streamUrl(camera.id, { width: 640, undistort })}
            alt={t('cameras.liveImage', { id: camera.id })}
          />
        ) : (
          <span className="muted">{stateLabel} …</span>
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
