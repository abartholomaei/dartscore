import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { ApiError, getJson, sendJson, type GameMode, type GameState, type Player } from '../api'
import { useLiveGame } from '../LiveGame'
import { useErrorText } from '../helpers'
import { PlayerForm } from './Players'
import styles from './NewGame.module.css'

type Participant = { key: string; playerId: number | null; guestName: string | null }
type InOut = 'single' | 'double' | 'master'

const START_SCORES = [301, 501, 701, 901]
const STORAGE_KEY = 'dartscore.newGame'

type Saved = {
  mode: GameMode
  startScore: number
  inRule: InOut
  outRule: InOut
  variant: 'standard' | 'cut_throat' | 'no_score'
  legs: number
  sets: number
  playerIds: number[]
}

function loadSaved(): Partial<Saved> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<Saved>
  } catch {
    return {}
  }
}

export default function NewGame() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const errorText = useErrorText()
  const { game: active, setGame } = useLiveGame()
  const saved = loadSaved()

  const [mode, setMode] = useState<GameMode>(saved.mode ?? 'x01')
  const [startScore, setStartScore] = useState(saved.startScore ?? 501)
  const [inRule, setInRule] = useState<InOut>(saved.inRule ?? 'single')
  const [outRule, setOutRule] = useState<InOut>(saved.outRule ?? 'double')
  const [variant, setVariant] = useState<Saved['variant']>(saved.variant ?? 'standard')
  const [legs, setLegs] = useState(saved.legs ?? 1)
  const [sets, setSets] = useState(saved.sets ?? 1)
  const [players, setPlayers] = useState<Player[]>([])
  const [participants, setParticipants] = useState<Participant[]>([])
  const [guestName, setGuestName] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getJson<Player[]>('/api/players')
      .then((list) => {
        setPlayers(list)
        // preselect the players of the last setup that still exist
        const ids = (loadSaved().playerIds ?? []).filter((id) => list.some((p) => p.id === id))
        setParticipants(ids.map((id) => ({ key: `p${id}`, playerId: id, guestName: null })))
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [errorText])

  const toggle = (player: Player) => {
    setParticipants((list) =>
      list.some((p) => p.playerId === player.id)
        ? list.filter((p) => p.playerId !== player.id)
        : list.length >= 8
          ? list
          : [...list, { key: `p${player.id}`, playerId: player.id, guestName: null }],
    )
  }

  const addGuest = () => {
    const name = guestName.trim() || t('newGame.guestN', { n: participants.filter((p) => p.guestName).length + 1 })
    setParticipants((list) => (list.length >= 8 ? list : [...list, { key: `g${Date.now()}`, playerId: null, guestName: name }]))
    setGuestName('')
  }

  const move = (index: number, delta: number) => {
    setParticipants((list) => {
      const next = [...list]
      const target = index + delta
      if (target < 0 || target >= next.length) return list
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  const shuffle = () => setParticipants((list) => [...list].sort(() => Math.random() - 0.5))

  const nameOf = (p: Participant) => p.guestName ?? players.find((pl) => pl.id === p.playerId)?.name ?? '?'
  const colorOf = (p: Participant) => players.find((pl) => pl.id === p.playerId)?.color ?? '#9e9e9e'

  const start = async () => {
    const running = active && !active.finished
    if (running && !window.confirm(t('newGame.confirmAbort'))) return
    const settings =
      mode === 'x01'
        ? { start_score: startScore, in_rule: inRule, out_rule: outRule, legs_to_win: legs, sets_to_win: sets }
        : { variant, legs_to_win: legs, sets_to_win: sets }
    const toStore: Saved = {
      mode, startScore, inRule, outRule, variant, legs, sets,
      playerIds: participants.flatMap((p) => (p.playerId === null ? [] : [p.playerId])),
    }  // prettier-ignore
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
    } catch {
      // private mode: the setup is just not remembered
    }
    try {
      const state = await sendJson<GameState>('POST', '/api/games', {
        mode,
        settings,
        abort_active: Boolean(running),
        players: participants.map((p) => (p.playerId === null ? { guest_name: p.guestName } : { player_id: p.playerId })),
      })
      setGame(state)
      void navigate('/play')
    } catch (err) {
      setError(err instanceof ApiError ? errorText(err) : String(err))
    }
  }

  const choice = <T extends string | number>(value: T, current: T, set: (v: T) => void, label: string) => (
    <button
      key={String(value)}
      type="button"
      className={value === current ? `${styles.chip} ${styles.chipActive}` : styles.chip}
      aria-pressed={value === current}
      onClick={() => set(value)}
    >
      {label}
    </button>
  )

  return (
    <>
      <h1 className={styles.title}>{t('newGame.title')}</h1>
      <div className={styles.layout}>
        <section className={`card ${styles.section}`}>
          <h2 className="cardTitle">{t('newGame.mode')}</h2>
          <div className={styles.chips}>
            {choice<GameMode>('x01', mode, setMode, 'X01')}
            {choice<GameMode>('cricket', mode, setMode, 'Cricket')}
          </div>

          {mode === 'x01' ? (
            <>
              <h3 className={styles.label}>{t('newGame.startScore')}</h3>
              <div className={styles.chips}>{START_SCORES.map((s) => choice(s, startScore, setStartScore, String(s)))}</div>
              <h3 className={styles.label}>{t('newGame.in')}</h3>
              <div className={styles.chips}>
                {(['single', 'double', 'master'] as InOut[]).map((r) => choice(r, inRule, setInRule, t(`newGame.rule.${r}`)))}
              </div>
              <h3 className={styles.label}>{t('newGame.out')}</h3>
              <div className={styles.chips}>
                {(['single', 'double', 'master'] as InOut[]).map((r) => choice(r, outRule, setOutRule, t(`newGame.rule.${r}`)))}
              </div>
            </>
          ) : (
            <>
              <h3 className={styles.label}>{t('newGame.variant')}</h3>
              <div className={styles.chips}>
                {(['standard', 'cut_throat', 'no_score'] as const).map((v) =>
                  choice(v, variant, setVariant, t(`newGame.variants.${v}`)),
                )}
              </div>
            </>
          )}

          <div className={styles.numbers}>
            <label>
              {t('newGame.legs')}
              <Stepper value={legs} min={1} max={21} onChange={setLegs} />
            </label>
            <label>
              {t('newGame.sets')}
              <Stepper value={sets} min={1} max={13} onChange={setSets} />
            </label>
          </div>
        </section>

        <section className={`card ${styles.section}`}>
          <h2 className="cardTitle">{t('newGame.players')}</h2>
          <div className={styles.chips}>
            {players.map((p) => {
              const on = participants.some((x) => x.playerId === p.id)
              return (
                <button
                  key={p.id}
                  type="button"
                  className={on ? `${styles.chip} ${styles.chipActive}` : styles.chip}
                  aria-pressed={on}
                  onClick={() => toggle(p)}
                >
                  <span className={styles.dot} style={{ background: p.color }} />
                  {p.name}
                </button>
              )
            })}
            <button type="button" className={styles.chip} onClick={() => setAdding(true)}>
              + {t('newGame.newProfile')}
            </button>
          </div>
          {adding && (
            <PlayerForm
              player={null}
              onDone={(created) => {
                setAdding(false)
                if (created) {
                  setPlayers((list) => [...list, created])
                  setParticipants((list) => [...list, { key: `p${created.id}`, playerId: created.id, guestName: null }])
                }
              }}
            />
          )}
          <div className={styles.guest}>
            <input
              value={guestName}
              maxLength={40}
              placeholder={t('newGame.guestPlaceholder')}
              onChange={(e) => setGuestName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addGuest()}
            />
            <button type="button" className="button" onClick={addGuest}>
              {t('newGame.addGuest')}
            </button>
          </div>

          <h3 className={styles.label}>{t('newGame.order')}</h3>
          {participants.length === 0 && <p className="muted">{t('newGame.noPlayers')}</p>}
          <ol className={styles.order}>
            {participants.map((p, i) => (
              <li key={p.key}>
                <span className={styles.dot} style={{ background: colorOf(p) }} />
                <span className={styles.orderName}>
                  {nameOf(p)}
                  {p.guestName && <span className="muted"> · {t('newGame.guest')}</span>}
                </span>
                <button type="button" aria-label={t('newGame.up')} onClick={() => move(i, -1)} disabled={i === 0}>
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={t('newGame.down')}
                  onClick={() => move(i, 1)}
                  disabled={i === participants.length - 1}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={t('newGame.remove')}
                  onClick={() => setParticipants((list) => list.filter((x) => x.key !== p.key))}
                >
                  ×
                </button>
              </li>
            ))}
          </ol>
          {participants.length > 1 && (
            <button type="button" className="button" onClick={shuffle}>
              {t('newGame.shuffle')}
            </button>
          )}
        </section>
      </div>
      {error && <p className="error">{error}</p>}
      <button className="button primary large" disabled={participants.length === 0} onClick={() => void start()}>
        {t('newGame.start')}
      </button>
    </>
  )
}

function Stepper({ value, min, max, onChange }: { value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <span className={styles.stepper}>
      <button type="button" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min}>
        −
      </button>
      <output>{value}</output>
      <button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max}>
        +
      </button>
    </span>
  )
}
