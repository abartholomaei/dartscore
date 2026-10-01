import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import {
  ApiError,
  getJson,
  getOptional,
  sendJson,
  snapshotUrl,
  type Calibration as CalibrationData,
  type CalibrationCatalog,
  type CalibrationPreview,
  type CameraStatus,
  type Point,
  type ScoreResult,
} from '../api'
import BoardDiagram from '../components/BoardDiagram'
import BoardOverlay from '../components/BoardOverlay'
import { useLiveGame } from '../LiveGame'
import { usePolling } from '../usePolling'
import LensCalibration from '../components/LensCalibration'
import styles from './Calibration.module.css'

type Snapshot = { url: string; width: number; height: number }
type Drag = { id: string; pointerId: number; startClient: Point; startPoint: Point }
type Loupe = { left: number; top: number; boxWidth: number; boxHeight: number }

const LOUPE_ZOOM = 6
const LOUPE_SIZE = 160
// a dragged marker moves this much of the pointer movement: an image pixel is several screen
// pixels wide, so moving 1:1 makes the marker jump from pixel to pixel
const DRAG_PRECISION = 0.25
// arrow keys move the active point by this many image pixels (with shift: 1 px)
const KEY_STEP = 0.25
// how close (screen px) a tap must be to grab an existing marker
const HIT_RADIUS = 28

export default function Calibration() {
  const { t } = useTranslation()
  const cameras = usePolling<CameraStatus[]>('/api/cameras', 5000)
  const [catalog, setCatalog] = useState<CalibrationCatalog | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  useEffect(() => {
    void getJson<CalibrationCatalog>('/api/calibration/points').then(setCatalog)
  }, [])

  const cameraList = cameras.kind === 'ok' ? cameras.data : []
  const cameraId = searchParams.get('camera') ?? cameraList[0]?.id ?? null
  const camera = cameraList.find((c) => c.id === cameraId) ?? null
  const step = searchParams.get('step') === 'lens' ? 'lens' : 'board'
  const select = (params: { camera?: string; step?: string }) =>
    setSearchParams({ camera: params.camera ?? cameraId ?? '', step: params.step ?? step })

  return (
    <>
      <h1 className={styles.title}>{t('calibration.title')}</h1>
      {cameras.kind === 'error' && (
        <p className="error">{t('cameras.backendUnreachable', { message: cameras.message })}</p>
      )}
      {cameraList.length > 0 && (
        <div className={styles.tabs} role="tablist">
          {cameraList.map((c) => (
            <button
              key={c.id}
              role="tab"
              aria-selected={c.id === cameraId}
              className={c.id === cameraId ? `${styles.tab} ${styles.tabActive}` : styles.tab}
              onClick={() => select({ camera: c.id })}
            >
              {c.id}
              <span className={c.board_calibrated ? styles.dotOk : styles.dotOpen} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
      {camera && (
        <div className={styles.tabs} role="tablist">
          {(['board', 'lens'] as const).map((s) => (
            <button
              key={s}
              role="tab"
              aria-selected={s === step}
              className={s === step ? `${styles.tab} ${styles.tabActive}` : styles.tab}
              onClick={() => select({ step: s })}
            >
              {t(`lens.step_${s}`)}
              {s === 'lens' && (
                <span className={camera.lens_calibrated ? styles.dotOk : styles.dotOpen} aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
      )}
      {camera && step === 'lens' && (
        <LensCalibration key={`lens-${camera.id}`} camera={camera} onChanged={() => undefined} />
      )}
      {camera && catalog && step === 'board' && (
        <CameraCalibration key={`${camera.id}-${camera.lens_calibrated}`} camera={camera} catalog={catalog} />
      )}
    </>
  )
}

function CameraCalibration({ camera, catalog }: { camera: CameraStatus; catalog: CalibrationCatalog }) {
  const { t } = useTranslation()
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [snapshotSrc, setSnapshotSrc] = useState(() =>
    snapshotUrl(camera.id, { width: 1920, undistort: camera.lens_calibrated }),
  )
  const [saved, setSaved] = useState<CalibrationData | null>(null)
  const [points, setPoints] = useState<Record<string, Point>>({})
  const [activeId, setActiveId] = useState<string | null>(catalog.points[0]?.id ?? null)
  const [mode, setMode] = useState<'edit' | 'test'>('edit')
  const [preview, setPreview] = useState<CalibrationPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [testHits, setTestHits] = useState<{ point: Point; result: ScoreResult }[]>([])
  const [drag, setDrag] = useState<Drag | null>(null)
  // the point the arrow keys move: the one placed or grabbed last, or picked in the list
  const [nudgeId, setNudgeId] = useState<string | null>(null)
  const [loupe, setLoupe] = useState<Loupe | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const { lastDart } = useLiveGame()
  const detectedHere = mode === 'test' ? lastDart?.hits.find((h) => h.camera_id === camera.id) : undefined

  const errorText = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.code) {
        return t(`calibration.errors.${err.code}`, { defaultValue: err.message })
      }
      return err instanceof Error ? err.message : String(err)
    },
    [t],
  )

  // load a saved calibration once
  useEffect(() => {
    const controller = new AbortController()
    getOptional<CalibrationData>(`/api/cameras/${camera.id}/calibration`, controller.signal)
      .then((data) => {
        setSaved(data)
        if (data) {
          setPoints(data.points)
          setMode('test')
          setActiveId(null)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(errorText(err))
      })
    return () => controller.abort()
  }, [camera.id, errorText])

  const placedIds = Object.keys(points)
  const enoughPoints = placedIds.length >= catalog.required

  // live preview of the fitted board while editing
  useEffect(() => {
    if (mode !== 'edit' || !enoughPoints) return
    const timer = window.setTimeout(() => {
      sendJson<CalibrationPreview>('POST', `/api/cameras/${camera.id}/calibration/preview`, { points })
        .then((p) => {
          setPreview(p)
          setError(null)
        })
        .catch((err: unknown) => {
          setPreview(null)
          setError(errorText(err))
        })
    }, 150)
    return () => window.clearTimeout(timer)
  }, [camera.id, points, mode, enoughPoints, errorText])

  const nextOpenPoint = (placed: Record<string, Point>) =>
    catalog.points.find((p) => !(p.id in placed))?.id ?? null

  const toImage = (clientX: number, clientY: number): { point: Point; rect: DOMRect } | null => {
    const box = boxRef.current
    if (!box || !snapshot) return null
    const rect = box.getBoundingClientRect()
    const x = ((clientX - rect.left) / rect.width) * snapshot.width
    const y = ((clientY - rect.top) / rect.height) * snapshot.height
    return {
      point: [Math.max(0, Math.min(snapshot.width, x)), Math.max(0, Math.min(snapshot.height, y))],
      rect,
    }
  }

  // the loupe shows the marker, which lags behind the pointer while dragging finely
  const updateLoupe = (point: Point, rect: DOMRect) => {
    if (!snapshot) return
    const scale = rect.width / snapshot.width
    setLoupe({ left: point[0] * scale, top: point[1] * scale, boxWidth: rect.width, boxHeight: rect.height })
  }

  const clampPoint = ([x, y]: Point): Point =>
    snapshot ? [Math.max(0, Math.min(snapshot.width, x)), Math.max(0, Math.min(snapshot.height, y))] : [x, y]

  const onPointerDown = async (e: React.PointerEvent<HTMLDivElement>) => {
    const hit = toImage(e.clientX, e.clientY)
    if (!hit || !snapshot) return

    if (mode === 'test') {
      try {
        const result = await sendJson<ScoreResult>('POST', `/api/cameras/${camera.id}/calibration/score`, {
          x: hit.point[0],
          y: hit.point[1],
        })
        setTestHits((hits) => [...hits.slice(-4), { point: hit.point, result }])
      } catch (err) {
        setError(errorText(err))
      }
      return
    }

    // grab an existing marker near the tap, otherwise place the active point here
    const scale = hit.rect.width / snapshot.width
    let target: string | null = null
    let best = HIT_RADIUS
    for (const [id, [x, y]] of Object.entries(points)) {
      const d = Math.hypot((x - hit.point[0]) * scale, (y - hit.point[1]) * scale)
      if (d < best) {
        best = d
        target = id
      }
    }
    // a new point lands where tapped; a grabbed one keeps its position until it is dragged
    let start = hit.point
    if (target === null) {
      if (!activeId) return
      target = activeId
      setPoints((p) => ({ ...p, [target as string]: hit.point }))
    } else {
      start = points[target]
    }
    setActiveId(target)
    setNudgeId(target)
    setDrag({ id: target, pointerId: e.pointerId, startClient: [e.clientX, e.clientY], startPoint: start })
    e.currentTarget.setPointerCapture(e.pointerId)
    updateLoupe(start, hit.rect)
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag || e.pointerId !== drag.pointerId || !snapshot || !boxRef.current) return
    const rect = boxRef.current.getBoundingClientRect()
    const perScreenPx = (snapshot.width / rect.width) * DRAG_PRECISION
    const point = clampPoint([
      drag.startPoint[0] + (e.clientX - drag.startClient[0]) * perScreenPx,
      drag.startPoint[1] + (e.clientY - drag.startClient[1]) * perScreenPx,
    ])
    setPoints((p) => ({ ...p, [drag.id]: point }))
    updateLoupe(point, rect)
  }

  // arrow keys nudge the point placed or grabbed last
  useEffect(() => {
    if (mode !== 'edit' || !nudgeId || !(nudgeId in points)) return
    const onKey = (e: KeyboardEvent) => {
      const step = e.shiftKey ? 1 : KEY_STEP
      const delta: Record<string, Point> = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, -step],
        ArrowDown: [0, step],
      }
      const d = delta[e.key]
      if (!d || (e.target instanceof HTMLElement && e.target.closest('input, textarea, select'))) return
      e.preventDefault()
      setPoints((p) => {
        const [x, y] = p[nudgeId]
        return { ...p, [nudgeId]: clampPoint([x + d[0], y + d[1]]) }
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const onPointerUp = () => {
    if (!drag) return
    setDrag(null)
    setLoupe(null)
    // continue with the next point that has not been placed yet
    setActiveId(nextOpenPoint(points))
  }

  const newSnapshot = () => {
    setSnapshot(null)
    setSnapshotSrc(snapshotUrl(camera.id, { width: 1920, undistort: camera.lens_calibrated }))
  }

  const startEditing = (id?: string) => {
    setMode('edit')
    setTestHits([])
    setMessage(null)
    setActiveId(id ?? nextOpenPoint(points) ?? catalog.points[0].id)
    setNudgeId(id ?? null)
  }

  const removePoint = (id: string) => {
    setPoints((p) => {
      const next = { ...p }
      delete next[id]
      return next
    })
    setActiveId(id)
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await sendJson<CalibrationData>('PUT', `/api/cameras/${camera.id}/calibration`, { points })
      setSaved(result)
      setMode('test')
      setActiveId(null)
      setMessage(t('calibration.saved'))
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const realign = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await sendJson<{ moved_px: number; calibration: CalibrationData }>(
        'POST',
        `/api/cameras/${camera.id}/calibration/realign`,
      )
      setSaved(result.calibration)
      setPoints(result.calibration.points)
      newSnapshot()
      setMessage(
        result.moved_px < 1
          ? t('calibration.realignNoMove')
          : t('calibration.realigned', { value: result.moved_px }),
      )
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm(t('calibration.confirmDelete'))) return
    setBusy(true)
    try {
      await sendJson<void>('DELETE', `/api/cameras/${camera.id}/calibration`)
      setSaved(null)
      startEditing()
      setMessage(t('calibration.deleted'))
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  // a preview only applies while editing with enough points
  const livePreview = mode === 'edit' && enoughPoints ? preview : null
  const overlay = mode === 'test' ? saved?.overlay : livePreview?.overlay
  const markerR = snapshot ? snapshot.width / 110 : 8
  const pointLabel = useMemo(
    () => (id: string) => {
      if (id === 'bull') return t('calibration.pointBull')
      const [a, b] = id.split('/')
      return t('calibration.pointBoundary', { a, b })
    },
    [t],
  )

  const activeLabel = activeId ? pointLabel(activeId) : null
  const rms = livePreview?.rms_px ?? saved?.rms_px
  const quality = rms === undefined ? null : rms < 1.5 ? 'good' : rms < 3 ? 'ok' : 'bad'

  return (
    <div className={styles.layout}>
      <section className={styles.imageColumn}>
        <p className={styles.instruction} aria-live="polite">
          {mode === 'test'
            ? t('calibration.testInstruction')
            : activeLabel
              ? t('calibration.placeInstruction', { point: activeLabel })
              : t('calibration.allPlaced')}
        </p>
        <div
          ref={boxRef}
          className={`${styles.imageBox} ${mode === 'edit' ? styles.editing : ''}`}
          style={snapshot ? { aspectRatio: `${snapshot.width} / ${snapshot.height}` } : undefined}
          onPointerDown={(e) => void onPointerDown(e)}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <img
            className={styles.image}
            src={snapshotSrc}
            alt={t('cameras.liveImage', { id: camera.id })}
            draggable={false}
            onLoad={(e) =>
              setSnapshot({
                url: snapshotSrc,
                width: e.currentTarget.naturalWidth,
                height: e.currentTarget.naturalHeight,
              })
            }
          />
          {snapshot && (
            <BoardOverlay
              overlay={overlay ?? { rings: [], wires: [], labels: [] }}
              width={snapshot.width}
              height={snapshot.height}
            >
              {Object.entries(points).map(([id, [x, y]]) => (
                <g key={id} className={id === (nudgeId ?? activeId) ? styles.markerActive : styles.marker}>
                  <circle cx={x} cy={y} r={markerR} />
                  <line x1={x - markerR * 1.6} y1={y} x2={x + markerR * 1.6} y2={y} />
                  <line x1={x} y1={y - markerR * 1.6} x2={x} y2={y + markerR * 1.6} />
                </g>
              ))}
              {detectedHere && (
                <g className={styles.detected}>
                  <circle cx={detectedHere.tip_px[0]} cy={detectedHere.tip_px[1]} r={markerR * 0.8} />
                </g>
              )}
              {testHits.map(({ point: [x, y], result }, i) => (
                <g key={i} className={styles.hit}>
                  <circle cx={x} cy={y} r={markerR * 0.6} />
                  <text x={x} y={y - markerR * 1.4} textAnchor="middle" fontSize={snapshot.width / 40}>
                    {result.label}
                  </text>
                </g>
              ))}
            </BoardOverlay>
          )}
          {loupe && snapshot && <Loupe loupe={loupe} src={snapshot.url} />}
        </div>
        <div className={styles.actions}>
          <button onClick={newSnapshot}>{t('calibration.newSnapshot')}</button>
          {mode === 'test' ? (
            <>
              <button onClick={() => startEditing()}>{t('calibration.edit')}</button>
              <button onClick={() => void realign()} disabled={busy} title={t('calibration.realignHint')}>
                {t('calibration.realign')}
              </button>
            </>
          ) : (
            <>
              <button onClick={() => { setPoints({}); setActiveId(catalog.points[0].id) }}>
                {t('calibration.reset')}
              </button>
              <button className={styles.primary} disabled={!enoughPoints || busy || !!error} onClick={() => void save()}>
                {t('calibration.save')}
              </button>
            </>
          )}
          {saved && (
            <button className={styles.danger} disabled={busy} onClick={() => void remove()}>
              {t('calibration.delete')}
            </button>
          )}
        </div>
      </section>

      <aside className={`card ${styles.side}`}>
        <BoardDiagram catalog={catalog} activeId={activeId} placedIds={placedIds} />
        <ol className={styles.pointList}>
          {catalog.points.map((p, i) => {
            const placed = p.id in points
            const err = livePreview?.errors_px[p.id]
            return (
              <li key={p.id} className={p.id === activeId ? styles.pointActive : undefined}>
                <button className={styles.pointButton} onClick={() => startEditing(p.id)}>
                  <span className={placed ? styles.dotOk : styles.dotOpen} aria-hidden="true" />
                  <span className={styles.pointName}>
                    {pointLabel(p.id)}
                    {i < catalog.required && <span className={styles.required}> *</span>}
                  </span>
                  {err !== undefined && enoughPoints && placedIds.length > catalog.required && (
                    <span className={styles.pointError}>{t('calibration.px', { value: err })}</span>
                  )}
                </button>
                {placed && mode === 'edit' && (
                  <button
                    className={styles.remove}
                    aria-label={t('calibration.removePoint')}
                    onClick={() => removePoint(p.id)}
                  >
                    ×
                  </button>
                )}
              </li>
            )
          })}
        </ol>
        <p className="muted">{t('calibration.requiredHint', { count: catalog.required })}</p>

        {quality && placedIds.length > catalog.required && (
          <p className={styles[quality]}>
            {t(`calibration.quality.${quality}`, { value: rms })}
          </p>
        )}
        {placedIds.length === catalog.required && mode === 'edit' && (
          <p className="muted">{t('calibration.morePointsHint')}</p>
        )}
        {mode === 'test' && saved && Object.keys(saved.points).length <= catalog.required && (
          <p className={styles.ok}>{t('calibration.onlyRequiredSaved')}</p>
        )}
        {mode === 'test' && lastDart && (
          <p>
            {t('detection.last', { label: lastDart.label, confidence: Math.round(lastDart.confidence * 100) })}
            {detectedHere && !detectedHere.used && <span className="muted"> · {t('calibration.outlier')}</span>}
          </p>
        )}
        {saved?.stale && <p className="error">{t('calibration.stale')}</p>}
        {saved?.drift_warning && (
          <p className="error">{t('calibration.drift', { value: saved.drift_px })}</p>
        )}
        {error && <p className="error">{error}</p>}
        {message && <p className="ok">{message}</p>}
      </aside>
    </div>
  )
}

function Loupe({ loupe, src }: { loupe: Loupe; src: string }) {
  // shown above the finger so it does not hide the spot being placed
  const size = LOUPE_SIZE
  const top = loupe.top - size - 24 < 0 ? loupe.top + 24 : loupe.top - size - 24
  const left = Math.max(0, Math.min(loupe.boxWidth - size, loupe.left - size / 2))
  return (
    <div
      className={styles.loupe}
      style={{
        width: size,
        height: size,
        left,
        top,
        backgroundImage: `url(${src})`,
        backgroundSize: `${loupe.boxWidth * LOUPE_ZOOM}px ${loupe.boxHeight * LOUPE_ZOOM}px`,
        backgroundPosition: `${-(loupe.left * LOUPE_ZOOM - size / 2)}px ${-(loupe.top * LOUPE_ZOOM - size / 2)}px`,
      }}
      aria-hidden="true"
    />
  )
}
