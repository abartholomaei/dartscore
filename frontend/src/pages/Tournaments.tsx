import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { getJson, sendJson, type GameState, type Player } from '../api'
import Avatar from '../components/Avatar'
import { useErrorText } from '../helpers'
import { useLiveGame } from '../LiveGame'
import setup from './NewGame.module.css'
import { Stepper, Toggle } from './NewGame'
import styles from './Tournaments.module.css'

type Summary = {
  id: number
  name: string
  format: 'knockout' | 'round_robin'
  mode: 'x01' | 'cricket'
  status: 'active' | 'finished'
  entries: number
  created_at: string
  champion: number | null
}
type Match = {
  id: number
  round: number
  slot: number
  a: number | null
  b: number | null
  game_id: number | null
  winner: number | null
  bye: boolean
  legs: [number, number] | null
}
type Detail = Summary & {
  settings: Record<string, string | number>
  players: { player_id: number | null; name: string; color: string }[]
  matches: Match[]
  standings: { entry: number; played: number; won: number; legs_for: number; legs_against: number }[] | null
}

/** List of tournaments and the form for a new one. */
export function TournamentList() {
  const { t, i18n } = useTranslation()
  const [list, setList] = useState<Summary[]>([])
  const [creating, setCreating] = useState(false)
  useEffect(() => {
    void getJson<Summary[]>('/api/tournaments').then(setList)
  }, [])
  return (
    <>
      <div className={styles.toolbar}>
        <h1 className={styles.title}>{t('tournaments.title')}</h1>
        {!creating && (
          <button className="button primary" onClick={() => setCreating(true)}>
            {t('tournaments.new')}
          </button>
        )}
      </div>
      {creating && <TournamentForm onCancel={() => setCreating(false)} />}
      {list.length === 0 && !creating && <p className="muted">{t('tournaments.empty')}</p>}
      <ul className={styles.list}>
        {list.map((item) => (
          <li key={item.id}>
            <Link to={`/tournaments/${item.id}`} className={`card ${styles.item}`}>
              <strong>{item.name}</strong>
              <span className="muted">
                {t(`tournaments.formats.${item.format}`)} · {t(`modes.${item.mode}`)} ·{' '}
                {t('tournaments.players', { count: item.entries })} · {new Date(item.created_at).toLocaleDateString(i18n.language)}
              </span>
              <span className={item.status === 'finished' ? styles.done : styles.running}>
                {t(`tournaments.status.${item.status}`)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}

function TournamentForm({ onCancel }: { onCancel: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const errorText = useErrorText()
  const [players, setPlayers] = useState<Player[]>([])
  const [name, setName] = useState('')
  const [format, setFormat] = useState<Summary['format']>('knockout')
  const [mode, setMode] = useState<Summary['mode']>('x01')
  const [startScore, setStartScore] = useState(501)
  const [legs, setLegs] = useState(2)
  const [selected, setSelected] = useState<number[]>([])
  const [guests, setGuests] = useState<string[]>([])
  const [guestName, setGuestName] = useState('')
  const [shuffle, setShuffle] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getJson<Player[]>('/api/players').then(setPlayers)
  }, [])

  const chip = <T extends string | number>(value: T, current: T, set: (v: T) => void, label: string) => (
    <button
      key={String(value)}
      type="button"
      className={value === current ? `${setup.chip} ${setup.chipActive}` : setup.chip}
      aria-pressed={value === current}
      onClick={() => set(value)}
    >
      {label}
    </button>
  )
  const count = selected.length + guests.length

  const submit = async () => {
    setError(null)
    try {
      const created = await sendJson<Detail>('POST', '/api/tournaments', {
        name: name.trim() || t('tournaments.defaultName'),
        format,
        mode,
        settings: mode === 'x01' ? { start_score: startScore, legs_to_win: legs } : { legs_to_win: legs },
        entries: [...selected.map((id) => ({ player_id: id })), ...guests.map((g) => ({ guest_name: g }))],
        shuffle,
      })
      void navigate(`/tournaments/${created.id}`)
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <section className={`card ${styles.form}`}>
      <label className={styles.field}>
        {t('tournaments.name')}
        <input value={name} maxLength={60} placeholder={t('tournaments.defaultName')} onChange={(e) => setName(e.target.value)} />
      </label>
      <h3 className={setup.label}>{t('tournaments.format')}</h3>
      <div className={setup.chips}>
        {(['knockout', 'round_robin'] as const).map((f) => chip(f, format, setFormat, t(`tournaments.formats.${f}`)))}
      </div>
      <h3 className={setup.label}>{t('newGame.mode')}</h3>
      <div className={setup.chips}>
        {chip<Summary['mode']>('x01', mode, setMode, 'X01')}
        {chip<Summary['mode']>('cricket', mode, setMode, 'Cricket')}
      </div>
      {mode === 'x01' && (
        <div className={setup.chips}>{[301, 501, 701].map((s) => chip(s, startScore, setStartScore, String(s)))}</div>
      )}
      <div className={setup.numbers}>
        <label>
          {t('tournaments.legsPerMatch')}
          <Stepper value={legs} min={1} max={11} onChange={setLegs} />
        </label>
      </div>
      <h3 className={setup.label}>{t('tournaments.participants', { count })}</h3>
      <div className={setup.chips}>
        {players.map((p) => {
          const on = selected.includes(p.id)
          return (
            <button
              key={p.id}
              type="button"
              className={on ? `${setup.chip} ${setup.chipActive}` : setup.chip}
              aria-pressed={on}
              onClick={() => setSelected((list) => (on ? list.filter((id) => id !== p.id) : [...list, p.id]))}
            >
              <Avatar name={p.name} color={p.color} avatar={p.avatar} size={24} />
              {p.name}
            </button>
          )
        })}
        {guests.map((g, i) => (
          <button
            key={`g${i}`}
            type="button"
            className={`${setup.chip} ${setup.chipActive}`}
            onClick={() => setGuests((list) => list.filter((_, j) => j !== i))}
          >
            {g} ✕
          </button>
        ))}
      </div>
      <div className={setup.guest}>
        <input
          value={guestName}
          maxLength={40}
          placeholder={t('newGame.guestPlaceholder')}
          onChange={(e) => setGuestName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && guestName.trim()) {
              setGuests((list) => [...list, guestName.trim()])
              setGuestName('')
            }
          }}
        />
        <button
          type="button"
          className="button"
          disabled={!guestName.trim()}
          onClick={() => {
            setGuests((list) => [...list, guestName.trim()])
            setGuestName('')
          }}
        >
          {t('newGame.addGuest')}
        </button>
      </div>
      <Toggle checked={shuffle} onChange={setShuffle} label={t('tournaments.shuffle')} />
      {error && <p className="error">{error}</p>}
      <div className={styles.actions}>
        <button className="button" onClick={onCancel}>
          {t('common.cancel')}
        </button>
        <button className="button primary" disabled={count < 2} onClick={() => void submit()}>
          {t('tournaments.create')}
        </button>
      </div>
    </section>
  )
}

/** One tournament: bracket (knockout) or table (round robin) with a "play" button per match. */
export function TournamentDetail() {
  const { t } = useTranslation()
  const { id } = useParams()
  const navigate = useNavigate()
  const errorText = useErrorText()
  const { game, setGame } = useLiveGame()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getJson<Detail>(`/api/tournaments/${id}`)
      .then(setDetail)
      .catch((err: unknown) => setError(errorText(err)))
  }, [id, errorText, game?.finished])

  if (error) return <p className="error">{error}</p>
  if (!detail) return <p className="muted">{t('cameras.loading')}</p>

  const busy = game !== null && !game.finished
  const play = async (match: Match) => {
    try {
      setGame(await sendJson<GameState>('POST', `/api/tournaments/${detail.id}/matches/${match.id}/start`))
      void navigate('/play')
    } catch (err) {
      setError(errorText(err))
    }
  }
  const name = (entry: number | null) => (entry === null ? null : detail.players[entry])
  const rounds = [...new Set(detail.matches.map((m) => m.round))]
  const lastRound = Math.max(...rounds)
  const champion = detail.champion !== null ? detail.players[detail.champion] : detail.standings && detail.status === 'finished' ? detail.players[detail.standings[0].entry] : null

  const card = (match: Match) => {
    if (match.bye) return null
    const ready = match.winner === null && match.a !== null && match.b !== null
    return (
      <div key={match.id} className={`card ${styles.match} ${ready ? styles.ready : ''}`}>
        {(['a', 'b'] as const).map((side, i) => {
          const entry = match[side]
          const p = name(entry)
          return (
            <div key={side} className={`${styles.side} ${match.winner !== null && match.winner === entry ? styles.winner : ''}`}>
              <span className={styles.dot} style={{ background: p?.color ?? 'transparent' }} />
              <span className={styles.name}>{p?.name ?? t('tournaments.open')}</span>
              <span className={styles.legs}>{match.legs ? match.legs[i] : ''}</span>
            </div>
          )
        })}
        {ready && (
          <button className="button primary" disabled={busy} onClick={() => void play(match)} title={busy ? t('tournaments.busy') : undefined}>
            {t('tournaments.play')}
          </button>
        )}
      </div>
    )
  }

  return (
    <>
      <div className={styles.toolbar}>
        <h1 className={styles.title}>{detail.name}</h1>
        <span className="muted">
          {t(`tournaments.formats.${detail.format}`)} · {t(`modes.${detail.mode}`)}
          {detail.settings.start_score ? ` ${detail.settings.start_score}` : ''} ·{' '}
          {t('play.firstTo', { count: Number(detail.settings.legs_to_win ?? 1) })}
        </span>
      </div>
      {champion && <div className={`card ${styles.champion}`}>🏆 {t('tournaments.champion', { name: champion.name })}</div>}

      {detail.format === 'knockout' ? (
        <div className={styles.bracket}>
          {rounds.map((round) => (
            <div key={round} className={styles.round}>
              <h2 className="cardTitle">
                {round === lastRound ? t('tournaments.final') : round === lastRound - 1 ? t('tournaments.semi') : t('tournaments.round', { round })}
              </h2>
              {detail.matches.filter((m) => m.round === round).map(card)}
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.robin}>
          <section className="card">
            <h2 className="cardTitle">{t('tournaments.table')}</h2>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th />
                  <th />
                  <th>{t('tournaments.played')}</th>
                  <th>{t('tournaments.won')}</th>
                  <th>{t('tournaments.legDiff')}</th>
                </tr>
              </thead>
              <tbody>
                {detail.standings?.map((row, i) => (
                  <tr key={row.entry}>
                    <td>{i + 1}.</td>
                    <th scope="row">{detail.players[row.entry].name}</th>
                    <td>{row.played}</td>
                    <td>{row.won}</td>
                    <td>
                      {row.legs_for}:{row.legs_against}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <div className={styles.robinMatches}>
            {rounds.map((round) => (
              <div key={round} className={styles.round}>
                <h2 className="cardTitle">{t('tournaments.round', { round })}</h2>
                {detail.matches.filter((m) => m.round === round).map(card)}
              </div>
            ))}
          </div>
        </div>
      )}
      {busy && <p className="muted">{t('tournaments.busy')}</p>}
    </>
  )
}
