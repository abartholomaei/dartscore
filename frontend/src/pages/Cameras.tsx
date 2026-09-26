import { useState } from 'react'
import { streamUrl, type CameraState, type CameraStatus } from '../api'
import { usePolling } from '../usePolling'
import styles from './Cameras.module.css'

const STATE_LABEL: Record<CameraState, string> = {
  starting: 'startet',
  running: 'läuft',
  reconnecting: 'verbindet neu',
  stopped: 'gestoppt',
}

export default function Cameras() {
  const cameras = usePolling<CameraStatus[]>('/api/cameras', 2000)
  const [undistort, setUndistort] = useState(false)

  const anyCalibrated = cameras.kind === 'ok' && cameras.data.some((c) => c.lens_calibrated)

  return (
    <>
      <div className={styles.toolbar}>
        <h1 className={styles.title}>Kameras</h1>
        <label className={styles.toggle} title={anyCalibrated ? '' : 'Noch keine Linsenkalibrierung'}>
          <input
            type="checkbox"
            checked={undistort}
            disabled={!anyCalibrated}
            onChange={(e) => setUndistort(e.target.checked)}
          />
          Entzerrt anzeigen
        </label>
      </div>

      {cameras.kind === 'loading' && <p className="muted">Lade …</p>}
      {cameras.kind === 'error' && <p className="error">Backend nicht erreichbar ({cameras.message})</p>}
      {cameras.kind === 'ok' && cameras.data.length === 0 && (
        <p className="muted">Keine Kameras konfiguriert. Siehe config.toml, Abschnitt [[cameras]].</p>
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
  const running = camera.state === 'running'
  const info = camera.info

  return (
    <article className={`card ${styles.camera}`}>
      <div className={styles.imageBox}>
        {running ? (
          <img
            className={styles.image}
            src={streamUrl(camera.id, { width: 640, undistort })}
            alt={`Livebild ${camera.id}`}
          />
        ) : (
          <span className="muted">{STATE_LABEL[camera.state]} …</span>
        )}
      </div>
      <header className={styles.cameraHeader}>
        <h2 className={styles.cameraTitle}>{camera.id}</h2>
        <span className={`${styles.badge} ${styles[camera.state]}`}>{STATE_LABEL[camera.state]}</span>
      </header>
      <dl className={styles.meta}>
        <dt>Bildrate</dt>
        <dd>{camera.fps.toFixed(1)} fps</dd>
        <dt>Format</dt>
        <dd>{info ? `${info.width}×${info.height} ${info.fourcc}` : '–'}</dd>
        <dt>Position</dt>
        <dd>{camera.position_deg}°</dd>
        <dt>Verloren</dt>
        <dd>{camera.dropped} Bilder</dd>
        <dt>Linse</dt>
        <dd>{camera.lens_calibrated ? 'kalibriert' : 'nicht kalibriert'}</dd>
        <dt>Quelle</dt>
        <dd className={styles.device}>{camera.source === 'synthetic' ? 'Simulation' : camera.device}</dd>
      </dl>
      {camera.last_error && <p className={`error ${styles.errorText}`}>{camera.last_error}</p>}
    </article>
  )
}
