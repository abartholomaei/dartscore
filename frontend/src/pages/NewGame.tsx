import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { ApiError, BOT_MODES, getJson, sendJson, PARTY_MODES, TRAINING_MODES, type GameMode, type GameState, type Player } from '../api'
import { useLiveGame } from '../LiveGame'
import { PENDING_KEY, useErrorText } from '../helpers'
import { PlayerForm } from './Players'
import Avatar from '../components/Avatar'
import RulesDialog, { RulesButton } from '../components/RulesDialog'
import styles from './NewGame.module.css'

type Participant = { key: string; playerId: number | null; guestName: string | null; botLevel?: number; botOf?: number }
type InOut = 'single' | 'double' | 'master'

const START_SCORES = [301, 501, 701, 901]
const STORAGE_KEY = 'dartscore.newGame'

type Saved = {
  mode: GameMode
  startScore: number
  inRule: InOut
  outRule: InOut
  variant: 'standard' | 'cut_throat' | 'no_score'
  training: TrainingOptions
  legs: number
  sets: number
  playerIds: number[]
}

type TrainingOptions = {
  atcVariant: 'single' | 'double' | 'triple'
  skipMultiples: boolean
  includeBull: boolean
  shanghaiRounds: number
  checkoutCount: number
  checkoutRange: string
  dartsPerTarget: number
  doublesOrder: 'sequential' | 'random'
  killerLives: number
  atcOrder: 'numbers' | 'board'
  halveItTargets: 'halve_it' | 'bermuda'
  cricketNumbers: 'standard' | 'random' | 'hidden'
  segNumber: number
  segRing: 'any' | 'single' | 'double' | 'triple'
  segEnd: 'darts' | 'hits'
  segLimit: number
  c121Attempts: number
  c121Darts: number
  gotchaTarget: number
  scoreRounds: number
}

const DEFAULT_TRAINING: TrainingOptions = {
  atcVariant: 'single',
  skipMultiples: false,
  includeBull: true,
  shanghaiRounds: 7,
  checkoutCount: 10,
  checkoutRange: '41-100',
  dartsPerTarget: 9,
  doublesOrder: 'sequential',
  killerLives: 3,
  atcOrder: 'numbers',
  halveItTargets: 'halve_it',
  cricketNumbers: 'standard',
  segNumber: 20,
  segRing: 'any',
  segEnd: 'darts',
  segLimit: 33,
  c121Attempts: 10,
  c121Darts: 9,
  gotchaTarget: 301,
  scoreRounds: 10,
}
const HANDICAP_SCORES = [101, 170, 201, 301, 401, 501, 601, 701, 901, 1001]
const BOT_LEVELS = [30, 40, 50, 60, 70, 80, 90, 100]
const CHECKOUT_RANGES = ['2-40', '41-100', '61-120', '101-170']

function trainingSettings(mode: GameMode, o: TrainingOptions): Record<string, unknown> {
  switch (mode) {
    case 'around_the_clock':
      return { variant: o.atcVariant, skip_multiples: o.skipMultiples, include_bull: o.includeBull, order: o.atcOrder }
    case 'shanghai':
      return { rounds: o.shanghaiRounds }
    case 'checkout_training': {
      const [min, max] = o.checkoutRange.split('-').map(Number)
      return { count: o.checkoutCount, min_score: min, max_score: max, darts_per_target: o.dartsPerTarget }
    }
    case 'doubles_training':
      return { order: o.doublesOrder, include_bull: o.includeBull }
    case 'killer':
      return { lives: o.killerLives }
    case 'halve_it':
      return { targets: o.halveItTargets }
    case 'segment_training': {
      const ring = o.segNumber === 25 && o.segRing === 'triple' ? 'any' : o.segRing
      const limits = o.segEnd === 'darts' ? [33, 66, 99] : [5, 10, 20, 50]
      return { number: o.segNumber, ring, end: o.segEnd, limit: limits.includes(o.segLimit) ? o.segLimit : limits[0] }
    }
    case 'checkout_121':
      return { attempts: o.c121Attempts, darts_per_attempt: o.c121Darts }
    case 'gotcha':
      return { target: o.gotchaTarget }
    case 'score_training':
      return { rounds: o.scoreRounds }
    default:
      return {}
  }
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
  const [training, setTraining] = useState<TrainingOptions>({ ...DEFAULT_TRAINING, ...saved.training })
  const setOption = <K extends keyof TrainingOptions>(key: K) => (value: TrainingOptions[K]) =>
    setTraining((o) => ({ ...o, [key]: value }))
  const isTraining = TRAINING_MODES.includes(mode) || PARTY_MODES.includes(mode)
  const [legs, setLegs] = useState(saved.legs ?? 1)
  const [sets, setSets] = useState(saved.sets ?? 1)
  const [players, setPlayers] = useState<Player[]>([])
  const [participants, setParticipants] = useState<Participant[]>([])
  const [guestName, setGuestName] = useState('')
  // "60" = bot with that average, "of:3" = personal bot imitating player 3
  const [botChoice, setBotChoice] = useState('60')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rulesFor, setRulesFor] = useState<GameMode | null>(null)
  // X01 handicap: a start score per participant (key -> score)
  // team games (X01/Cricket): team number per participant key
  const [teamPlay, setTeamPlay] = useState(false)
  const [teamCount, setTeamCount] = useState(2)
  const [teamOf, setTeamOf] = useState<Record<string, number>>({})
  const [handicap, setHandicap] = useState(false)
  const [handicapScores, setHandicapScores] = useState<Record<string, number>>({})

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
    // the first selected player's preferred mode is preselected
    if (participants.length === 0 && player.default_mode) setMode(player.default_mode)
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

  const addBot = () => {
    setParticipants((list) =>
      list.length >= 8
        ? list
        : [
            ...list,
            botChoice.startsWith('of:')
              ? { key: `b${Date.now()}`, playerId: null, guestName: null, botOf: Number(botChoice.slice(3)) }
              : { key: `b${Date.now()}`, playerId: null, guestName: null, botLevel: Number(botChoice) },
          ],
    )
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

  const nameOf = (p: Participant) =>
    (p.botOf ? t('newGame.botOf', { name: players.find((pl) => pl.id === p.botOf)?.name ?? '?' }) : null) ??
    (p.botLevel ? `Bot ${p.botLevel}` : null) ?? p.guestName ?? players.find((pl) => pl.id === p.playerId)?.name ?? '?'
  const colorOf = (p: Participant) => players.find((pl) => pl.id === p.playerId)?.color ?? '#9e9e9e'

  const teamIndex = (key: string, i: number) => teamOf[key] ?? i % teamCount
  const teams = () =>
    Array.from({ length: teamCount }, (_, t) =>
      participants.map((p, i) => (teamIndex(p.key, i) === t ? i : -1)).filter((i) => i >= 0),
    )

  const buildRequest = () => {
    const settings =
      mode === 'x01'
        ? {
            start_score: startScore,
            in_rule: inRule,
            out_rule: outRule,
            legs_to_win: legs,
            sets_to_win: sets,
            ...(handicap ? { start_scores: participants.map((p) => handicapScores[p.key] ?? null) } : {}),
            ...(teamPlay ? { teams: teams() } : {}),
          }
        : mode === 'cricket'
          ? {
              variant,
              numbers: training.cricketNumbers,
              legs_to_win: legs,
              sets_to_win: sets,
              ...(teamPlay ? { teams: teams() } : {}),
            }
          : trainingSettings(mode, training)
    return {
      mode,
      settings,
      players: participants.map((p) =>
        p.botOf ? { bot_of: p.botOf } : p.botLevel ? { bot_level: p.botLevel } : p.playerId === null ? { guest_name: p.guestName } : { player_id: p.playerId },
      ),
    }
  }

  const remember = () => {
    const toStore: Saved = {
      mode, startScore, inRule, outRule, variant, training, legs, sets,
      playerIds: participants.flatMap((p) => (p.playerId === null ? [] : [p.playerId])),
    }  // prettier-ignore
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
    } catch {
      // private mode: the setup is just not remembered
    }
  }

  const launch = async (body: object) => {
    const running = active && !active.finished
    if (running && !window.confirm(t('newGame.confirmAbort'))) return
    try {
      const state = await sendJson<GameState>('POST', '/api/games', { ...body, abort_active: Boolean(running) })
      setGame(state)
      void navigate('/play')
    } catch (err) {
      setError(err instanceof ApiError ? errorText(err) : String(err))
    }
  }

  const start = async () => {
    remember()
    await launch(buildRequest())
  }

  // bull-off first: the game itself is started afterwards with the winner throwing first
  const bullOff = async () => {
    remember()
    const request = buildRequest()
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(request))
    } catch {
      // without storage the game has to be started by hand afterwards
    }
    await launch({ mode: 'bull_off', settings: {}, players: request.players })
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
          <div className={styles.modeHeader}>
            <h2 className="cardTitle">{t('newGame.mode')}</h2>
            <RulesButton mode={mode} onOpen={setRulesFor} />
          </div>
          {rulesFor && <RulesDialog mode={rulesFor} onClose={() => setRulesFor(null)} />}
          <div className={styles.chips}>
            {choice<GameMode>('x01', mode, setMode, 'X01')}
            {choice<GameMode>('cricket', mode, setMode, 'Cricket')}
          </div>
          <h3 className={styles.label}>{t('newGame.training')}</h3>
          <div className={styles.chips}>
            {TRAINING_MODES.map((m) => choice<GameMode>(m, mode, setMode, t(`modes.${m}`)))}
          </div>
          <h3 className={styles.label}>{t('newGame.party')}</h3>
          <div className={styles.chips}>
            {PARTY_MODES.map((m) => choice<GameMode>(m, mode, setMode, t(`modes.${m}`)))}
          </div>

          {mode === 'x01' && (
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
              <Toggle checked={handicap} onChange={setHandicap} label={t('newGame.handicap')} />
              {handicap && <p className="muted">{t('newGame.handicapHint')}</p>}
            </>
          )}
          {mode === 'cricket' && (
            <>
              <h3 className={styles.label}>{t('newGame.variant')}</h3>
              <div className={styles.chips}>
                {(['standard', 'cut_throat', 'no_score'] as const).map((v) =>
                  choice(v, variant, setVariant, t(`newGame.variants.${v}`)),
                )}
              </div>
              <h3 className={styles.label}>{t('newGame.cricketNumbers')}</h3>
              <div className={styles.chips}>
                {(['standard', 'random', 'hidden'] as const).map((v) =>
                  choice(v, training.cricketNumbers, setOption('cricketNumbers'), t(`newGame.cricketNumberSets.${v}`)),
                )}
              </div>
            </>
          )}
          {mode === 'around_the_clock' && (
            <>
              <h3 className={styles.label}>{t('newGame.ring')}</h3>
              <div className={styles.chips}>
                {(['single', 'double', 'triple'] as const).map((v) =>
                  choice(v, training.atcVariant, setOption('atcVariant'), t(`newGame.rings.${v}`)),
                )}
              </div>
              <h3 className={styles.label}>{t('newGame.atcOrder')}</h3>
              <div className={styles.chips}>
                {(['numbers', 'board'] as const).map((v) =>
                  choice(v, training.atcOrder, setOption('atcOrder'), t(`newGame.atcOrders.${v}`)),
                )}
              </div>
              <Toggle checked={training.skipMultiples} onChange={setOption('skipMultiples')} label={t('newGame.skipMultiples')} />
              <Toggle checked={training.includeBull} onChange={setOption('includeBull')} label={t('newGame.includeBull')} />
            </>
          )}
          {mode === 'shanghai' && (
            <>
              <h3 className={styles.label}>{t('newGame.rounds')}</h3>
              <div className={styles.chips}>
                {[7, 20].map((r) => choice(r, training.shanghaiRounds, setOption('shanghaiRounds'), String(r)))}
              </div>
            </>
          )}
          {mode === 'checkout_training' && (
            <>
              <h3 className={styles.label}>{t('newGame.checkoutRange')}</h3>
              <div className={styles.chips}>
                {CHECKOUT_RANGES.map((r) => choice(r, training.checkoutRange, setOption('checkoutRange'), r))}
              </div>
              <h3 className={styles.label}>{t('newGame.dartsPerTarget')}</h3>
              <div className={styles.chips}>
                {[3, 6, 9].map((d) => choice(d, training.dartsPerTarget, setOption('dartsPerTarget'), String(d)))}
              </div>
              <div className={styles.numbers}>
                <label>
                  {t('newGame.targetCount')}
                  <Stepper value={training.checkoutCount} min={1} max={50} onChange={setOption('checkoutCount')} />
                </label>
              </div>
            </>
          )}
          {mode === 'doubles_training' && (
            <>
              <h3 className={styles.label}>{t('newGame.order')}</h3>
              <div className={styles.chips}>
                {(['sequential', 'random'] as const).map((o) =>
                  choice(o, training.doublesOrder, setOption('doublesOrder'), t(`newGame.orders.${o}`)),
                )}
              </div>
              <Toggle checked={training.includeBull} onChange={setOption('includeBull')} label={t('newGame.includeBull')} />
            </>
          )}
          {mode === 'bobs_27' && <p className="muted">{t('newGame.bobsHint')}</p>}
          {mode === 'segment_training' && (
            <>
              <h3 className={styles.label}>{t('newGame.segment')}</h3>
              <div className={styles.chips}>
                {[0, 20, 19, 18, 17, 16, 15, 25].map((n) =>
                  choice(n, training.segNumber, setOption('segNumber'), n === 0 ? t('newGame.randomTarget') : n === 25 ? 'Bull' : String(n)),
                )}
                <select
                  className={styles.chip}
                  aria-label={t('newGame.segment')}
                  value={training.segNumber}
                  onChange={(e) => setOption('segNumber')(Number(e.target.value))}
                >
                  {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                  <option value={25}>Bull</option>
                  <option value={0}>{t('newGame.randomTarget')}</option>
                </select>
              </div>
              <h3 className={styles.label}>{t('newGame.ring')}</h3>
              <div className={styles.chips}>
                {(['any', 'single', 'double', 'triple'] as const)
                  .filter((r) => !(training.segNumber === 25 && r === 'triple'))
                  .map((r) => choice(r, training.segRing, setOption('segRing'), t(`newGame.segRings.${r}`)))}
              </div>
              <h3 className={styles.label}>{t('newGame.segEnd')}</h3>
              <div className={styles.chips}>
                {(['darts', 'hits'] as const).map((e) =>
                  choice(e, training.segEnd, (v: 'darts' | 'hits') => {
                    setOption('segEnd')(v)
                    setOption('segLimit')(v === 'darts' ? 33 : 10)
                  }, t(`newGame.segEnds.${e}`)),
                )}
              </div>
              <div className={styles.chips}>
                {(training.segEnd === 'darts' ? [33, 66, 99] : [5, 10, 20, 50]).map((n) =>
                  choice(n, training.segLimit, setOption('segLimit'), String(n)),
                )}
              </div>
            </>
          )}
          {mode === 'checkout_121' && (
            <>
              <h3 className={styles.label}>{t('newGame.dartsPerAttempt')}</h3>
              <div className={styles.chips}>
                {[3, 6, 9].map((d) => choice(d, training.c121Darts, setOption('c121Darts'), String(d)))}
              </div>
              <div className={styles.numbers}>
                <label>
                  {t('newGame.attempts')}
                  <Stepper value={training.c121Attempts} min={1} max={50} onChange={setOption('c121Attempts')} />
                </label>
              </div>
              <p className="muted">{t('newGame.checkout121Hint')}</p>
            </>
          )}
          {mode === 'score_training' && (
            <>
              <h3 className={styles.label}>{t('newGame.rounds')}</h3>
              <div className={styles.chips}>
                {[5, 10, 20, 33].map((r) => choice(r, training.scoreRounds, setOption('scoreRounds'), String(r)))}
              </div>
            </>
          )}
          {mode === 'killer' && (
            <>
              <div className={styles.numbers}>
                <label>
                  {t('newGame.lives')}
                  <Stepper value={training.killerLives} min={1} max={9} onChange={setOption('killerLives')} />
                </label>
              </div>
              <p className="muted">{t('newGame.killerHint')}</p>
            </>
          )}
          {mode === 'halve_it' && (
            <>
              <h3 className={styles.label}>{t('newGame.sequence')}</h3>
              <div className={styles.chips}>
                {(['halve_it', 'bermuda'] as const).map((v) =>
                  choice(v, training.halveItTargets, setOption('halveItTargets'), t(`newGame.sequences.${v}`)),
                )}
              </div>
              <p className="muted">{training.halveItTargets === 'bermuda' ? t('newGame.bermudaHint') : t('newGame.halveItHint')}</p>
            </>
          )}
          {mode === 'gotcha' && (
            <>
              <h3 className={styles.label}>{t('newGame.goal')}</h3>
              <div className={styles.chips}>
                {[101, 201, 301, 501].map((g) => choice(g, training.gotchaTarget, setOption('gotchaTarget'), String(g)))}
              </div>
              <p className="muted">{t('newGame.gotchaHint')}</p>
            </>
          )}

          {!isTraining && (
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
          )}
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
                  <Avatar name={p.name} color={p.color} avatar={p.avatar} size={24} />
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
          {BOT_MODES.includes(mode) && (
            <div className={styles.guest}>
              <select value={botChoice} onChange={(e) => setBotChoice(e.target.value)} aria-label={t('newGame.botLevel')}>
                {BOT_LEVELS.map((level) => (
                  <option key={level} value={String(level)}>
                    {t('newGame.botAverage', { average: level })}
                  </option>
                ))}
                {players.length > 0 && (
                  <optgroup label={t('newGame.personalBots')}>
                    {players.map((p) => (
                      <option key={p.id} value={`of:${p.id}`}>
                        {t('newGame.botOf', { name: p.name })}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              <button type="button" className="button" onClick={addBot}>
                {t('newGame.addBot')}
              </button>
            </div>
          )}

          <h3 className={styles.label}>{t('newGame.order')}</h3>
          {(mode === 'x01' || mode === 'cricket') && participants.length >= 3 && (
            <div className={styles.teamToggle}>
              <Toggle checked={teamPlay} onChange={setTeamPlay} label={t('newGame.teams')} />
              {teamPlay && (
                <label>
                  {t('newGame.teamCount')}
                  <Stepper value={teamCount} min={2} max={4} onChange={setTeamCount} />
                </label>
              )}
            </div>
          )}
          {teamPlay && <p className="muted">{t('newGame.teamsHint')}</p>}
          {participants.length === 0 && <p className="muted">{t('newGame.noPlayers')}</p>}
          <ol className={styles.order}>
            {participants.map((p, i) => (
              <li key={p.key}>
                <span className={styles.dot} style={{ background: colorOf(p) }} />
                <span className={styles.orderName}>
                  {nameOf(p)}
                  {p.guestName && <span className="muted"> · {t('newGame.guest')}</span>}
                  {(p.botLevel || p.botOf) && <span className="muted"> · {t('newGame.bot')}</span>}
                </span>
                {teamPlay && (mode === 'x01' || mode === 'cricket') && (
                  <span className={styles.teamChips}>
                    {Array.from({ length: teamCount }, (_, tn) => (
                      <button
                        key={tn}
                        type="button"
                        className={teamIndex(p.key, i) === tn ? styles.teamActive : undefined}
                        aria-pressed={teamIndex(p.key, i) === tn}
                        onClick={() => setTeamOf((m) => ({ ...m, [p.key]: tn }))}
                      >
                        {String.fromCharCode(65 + tn)}
                      </button>
                    ))}
                  </span>
                )}
                {mode === 'x01' && handicap && (
                  <select
                    className={styles.handicap}
                    aria-label={t('newGame.handicapFor', { name: nameOf(p) })}
                    value={handicapScores[p.key] ?? startScore}
                    onChange={(e) => setHandicapScores((h) => ({ ...h, [p.key]: Number(e.target.value) }))}
                  >
                    {HANDICAP_SCORES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                )}
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
      <div className={styles.startRow}>
        <button className="button primary large" disabled={participants.length === 0} onClick={() => void start()}>
          {t('newGame.start')}
        </button>
        {participants.length > 1 && (
          <button className="button large" onClick={() => void bullOff()} title={t('newGame.bullOffHint')}>
            {t('newGame.bullOff')}
          </button>
        )}
      </div>
    </>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className={styles.toggle}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

export function Stepper({ value, min, max, onChange }: { value: number; min: number; max: number; onChange: (v: number) => void }) {
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
