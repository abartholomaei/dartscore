import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getJson, sendJson, type GameState, type Point } from '../api'
import { useErrorText } from '../helpers'
import styles from './VisitPhotos.module.css'

type Photo = { cameras: string[]; tips: Record<string, Point>; used: string[]; detected: string | null }
export type Visit = {
  set: number
  leg: number
  turn_index: number
  player: number
  darts: string[]
  seqs: (number | null)[]
  total: number
  bust: boolean
  photos: (Photo | null)[]
}
export type VisitRef = { set: number; leg: number; turn_index: number }
type CameraVerdict = { camera_id: string; label: string | null; found: number; used: boolean }
type Verdict = { label: string | null; unanimous: boolean; cameras: CameraVerdict[] }

/** Camera images of one visit: the view after its last detected dart, with numbered markers
 *  where the detection saw each dart's tip. */
export default function VisitPhotos({
  gameId,
  initial,
  playerNames,
  onClose,
  onCorrected,
}: {
  gameId: number
  initial: VisitRef
  playerNames: string[]
  onClose: () => void
  // set when the game is running: referee results can then be applied
  onCorrected?: (state: GameState) => void
}) {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const dialog = useRef<HTMLDialogElement>(null)
  const [visits, setVisits] = useState<Visit[] | null>(null)
  const [index, setIndex] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enlarged, setEnlarged] = useState<string | null>(null)
  const [verdicts, setVerdicts] = useState<Record<number, Verdict | 'loading'>>({})
  const [reload, setReload] = useState(0)

  const review = async (seq: number) => {
    setVerdicts((v) => ({ ...v, [seq]: 'loading' }))
    try {
      const verdict = await getJson<Verdict>(`/api/games/${gameId}/darts/${seq}/review`)
      setVerdicts((v) => ({ ...v, [seq]: verdict }))
    } catch (err) {
      setError(errorText(err))
      setVerdicts((v) => {
        const next = { ...v }
        delete next[seq]
        return next
      })
    }
  }

  const apply = async (seq: number, label: string) => {
    try {
      const state = await sendJson<GameState>('PUT', `/api/games/active/events/${seq}`, { dart: label })
      onCorrected?.(state)
      setReload((r) => r + 1)
    } catch (err) {
      setError(errorText(err))
    }
  }

  useEffect(() => {
    dialog.current?.showModal()
  }, [])

  useEffect(() => {
    getJson<Visit[]>(`/api/games/${gameId}/visits`)
      .then((list) => {
        setVisits(list)
        const found = list.findIndex(
          (v) => v.set === initial.set && v.leg === initial.leg && v.turn_index === initial.turn_index,
        )
        setIndex((current) => current ?? (found >= 0 ? found : list.length - 1))
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [gameId, initial, errorText, reload])

  const visit = visits && index !== null ? visits[index] : null
  // the last dart of the visit that has photos: its "after" images show all darts of the visit
  const lastPhoto = visit ? visit.photos.map((p, i) => (p ? i : -1)).filter((i) => i >= 0).at(-1) : undefined
  const cameras = visit && lastPhoto !== undefined ? (visit.photos[lastPhoto]?.cameras ?? []) : []

  return (
    <dialog ref={dialog} className={styles.dialog} onClose={onClose} onClick={(e) => e.target === dialog.current && dialog.current?.close()}>
      <div className={styles.header}>
        <button className="button" onClick={() => setIndex((i) => (i !== null && i > 0 ? i - 1 : i))} disabled={!index}>
          ←
        </button>
        <div className={styles.title}>
          {visit ? (
            <>
              <strong>{playerNames[visit.player]}</strong>
              <span className="muted">
                {' '}
                · {t('photos.legTurn', { leg: visit.leg, turn: visit.turn_index + 1 })} ·{' '}
                {visit.bust ? t('play.bust') : visit.total}
              </span>
            </>
          ) : (
            t('cameras.loading')
          )}
        </div>
        <button
          className="button"
          onClick={() => setIndex((i) => (i !== null && visits && i < visits.length - 1 ? i + 1 : i))}
          disabled={!visits || index === null || index >= visits.length - 1}
        >
          →
        </button>
        <button className="button" onClick={() => dialog.current?.close()} aria-label={t('common.close')}>
          ✕
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {visit && (
        <>
          <ol className={styles.darts}>
            {visit.darts.map((label, i) => {
              const photo = visit.photos[i]
              const seq = visit.seqs[i]
              const verdict = seq !== null ? verdicts[seq] : undefined
              return (
                <li key={i}>
                  <span className={styles.number}>{i + 1}</span>
                  <strong>{label}</strong>
                  {photo?.detected && photo.detected !== label && (
                    <span className="muted"> {t('photos.detectedAs', { label: photo.detected })}</span>
                  )}
                  {!photo && <span className="muted"> {t('photos.noPhoto')}</span>}
                  {photo && seq !== null && verdict === undefined && (
                    <button className={styles.review} onClick={() => void review(seq)}>
                      {t('photos.review')}
                    </button>
                  )}
                  {verdict === 'loading' && <span className="muted"> {t('photos.reviewing')}</span>}
                  {verdict && verdict !== 'loading' && (
                    <span className={styles.verdict}>
                      {t('photos.verdict', { label: verdict.label ?? '–' })}{' '}
                      <span className="muted">
                        ({verdict.cameras.map((c) => `${c.camera_id}: ${c.label ?? '–'}`).join(', ')})
                      </span>
                      {verdict.label && verdict.label !== label && onCorrected && (
                        <button className={styles.review} onClick={() => void apply(seq as number, verdict.label as string)}>
                          {t('photos.apply', { label: verdict.label })}
                        </button>
                      )}
                      {verdict.label === label && <span className={styles.confirmed}> ✓</span>}
                    </span>
                  )}
                </li>
              )
            })}
          </ol>
          {lastPhoto === undefined ? (
            <p className="muted">{t('photos.none')}</p>
          ) : (
            <div className={styles.cameras}>
              {cameras.map((cid) => (
                <CameraPhoto
                  key={`${index}-${cid}`}
                  src={`/api/games/${gameId}/darts/${visit.seqs[lastPhoto]}/${encodeURIComponent(cid)}.jpg`}
                  camera={cid}
                  tips={visit.photos.map((p) => (p ? (p.tips[cid] ?? null) : null))}
                  used={visit.photos.map((p) => !!p?.used.includes(cid))}
                  large={enlarged === cid}
                  onToggle={() => setEnlarged((c) => (c === cid ? null : cid))}
                />
              ))}
            </div>
          )}
          <p className="muted">{t('photos.hint')}</p>
        </>
      )}
    </dialog>
  )
}

function CameraPhoto({
  src,
  camera,
  tips,
  used,
  large,
  onToggle,
}: {
  src: string
  camera: string
  tips: (Point | null)[]
  used: boolean[]
  large: boolean
  onToggle: () => void
}) {
  const [size, setSize] = useState<[number, number] | null>(null)
  return (
    <figure className={large ? `${styles.photo} ${styles.large}` : styles.photo}>
      <button className={styles.photoButton} onClick={onToggle} aria-pressed={large}>
        <img src={src} alt={camera} onLoad={(e) => setSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])} />
        {size && (
          <svg viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none" className={styles.overlay}>
            {tips.map((tip, i) =>
              tip ? (
                <g key={i} className={used[i] ? styles.tipUsed : styles.tipIgnored}>
                  <circle cx={tip[0]} cy={tip[1]} r={size[0] / 70} />
                  <text x={tip[0]} y={tip[1] - size[0] / 45} textAnchor="middle" fontSize={size[0] / 28}>
                    {i + 1}
                  </text>
                </g>
              ) : null,
            )}
          </svg>
        )}
      </button>
      <figcaption>{camera}</figcaption>
    </figure>
  )
}
