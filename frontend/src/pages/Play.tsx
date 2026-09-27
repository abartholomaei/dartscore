import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { sendJson, type CricketVariant, type GamePlayer, type GameState, type InOutRule } from '../api'
import Avatar from '../components/Avatar'
import RulesDialog, { RulesButton } from '../components/RulesDialog'
import DartBoard from '../components/DartBoard'
import DetectionBadge from '../components/DetectionBadge'
import VisitPhotos, { type VisitRef } from '../components/VisitPhotos'
import { dartLabel, dartPoints } from '../dart'
import { useLiveGame } from '../LiveGame'
import { useCaller } from '../caller'
import { PENDING_KEY, useErrorText, type PendingGame } from '../helpers'
import { trainingTarget, useTargetText } from '../target'
import styles from './Play.module.css'

type InputMode = 'pad' | 'board'

// automatic detections below this confidence are marked for checking
const LOW_CONFIDENCE = 0.5
const DISPLAY_KEY = 'dartscore.displayMode'

export default function Play() {
  const { t } = useTranslation()
  const { game, connected } = useLiveGame()
  const celebration = useCaller(game)
  const banner = celebration && (
    <div key={celebration.key} className={`${styles.celebration} ${styles[`celebration_${celebration.kind}`]}`} aria-live="assertive">
      {celebration.text}
    </div>
  )

  if (!connected && !game) return <p className="muted">{t('play.connecting')}</p>
  if (!game) {
    return (
      <div className={`card ${styles.empty}`}>
        <p>{t('play.noGame')}</p>
        <Link to="/play/new" className="button primary large">
          {t('home.newGame')}
        </Link>
      </div>
    )
  }
  if (game.finished && game.mode === 'bull_off') return <BullOffResult game={game} />
  return (
    <>
      {banner}
      {game.finished ? <Finished game={game} /> : <Running game={game} />}
    </>
  )
}

function Running({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const { setGame } = useLiveGame()
  const errorText = useErrorText()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [inputMode, setInputMode] = useState<InputMode>('pad')
  // display mode: only the scoreboard, large (remembered per browser)
  const [displayMode, setDisplayMode] = useState(() => {
    try {
      return localStorage.getItem(DISPLAY_KEY) === '1'
    } catch {
      return false
    }
  })
  const toggleDisplayMode = () => {
    const next = !displayMode
    setDisplayMode(next)
    try {
      localStorage.setItem(DISPLAY_KEY, next ? '1' : '0')
    } catch {
      // private mode
    }
    if (next && !document.fullscreenElement) void document.documentElement.requestFullscreen?.().catch(() => undefined)
    if (!next && document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
  }
  const [multiplier, setMultiplier] = useState<1 | 2 | 3>(1)
  // index of a dart of the shown turn that the next input replaces
  const [correcting, setCorrecting] = useState<number | null>(null)

  // Inputs are queued, never dropped: fast taps are sent one after another, each seeing
  // the state returned by the previous request.
  const queue = useRef<Promise<void>>(Promise.resolve())
  const latest = useRef(game)
  useEffect(() => {
    latest.current = game
  }, [game])
  const pending = useRef(0)

  const call = (fn: (state: GameState) => Promise<GameState>) => {
    pending.current += 1
    setBusy(true)
    setError(null)
    queue.current = queue.current.then(async () => {
      try {
        const state = await fn(latest.current)
        latest.current = state
        setGame(state)
      } catch (err) {
        setError(errorText(err))
      } finally {
        pending.current -= 1
        if (pending.current === 0) setBusy(false)
      }
    })
    return queue.current
  }

  const enter = (label: string) => {
    const index = correcting
    setCorrecting(null)
    setMultiplier(1)
    return call(async (state) => {
      if (index !== null) {
        return sendJson<GameState>('PUT', '/api/games/active/darts', { turn_index: -1, dart_index: index, dart: label })
      }
      // entering a dart after a complete turn means the darts were pulled
      if (state.awaiting_next) await sendJson<GameState>('POST', '/api/games/active/next')
      return sendJson<GameState>('POST', '/api/games/active/throws', { dart: label })
    })
  }

  // the selected dart, or the last one of the turn, fell out of the board
  const bounce = () => {
    const index = correcting ?? shownDarts.length - 1
    setCorrecting(null)
    if (index < 0) return
    return call(() =>
      sendJson<GameState>('PUT', '/api/games/active/darts', { turn_index: -1, dart_index: index, bounce: true }),
    )
  }

  const next = () => call(() => sendJson<GameState>('POST', '/api/games/active/next'))
  const undo = () => {
    setCorrecting(null)
    return call(() => sendJson<GameState>('POST', '/api/games/active/undo'))
  }

  const turn = game.turn
  const turnDarts = turn?.darts ?? []
  const showTurn = turn && (turn.player === game.current_player || game.awaiting_next)
  const shownDarts = showTurn ? turnDarts : []
  const current = game.players[showTurn && turn ? turn.player : game.current_player]
  const legWinner = game.leg_winner !== null && game.awaiting_next ? game.players[game.leg_winner] : null

  return (
    <div className={displayMode ? `${styles.layout} ${styles.displayMode}` : styles.layout}>
      <section className={styles.scores}>
        <MatchInfo game={game} />
        <TargetBanner game={game} />
        {game.mode === 'x01' ? (
          <X01Scores game={game} />
        ) : game.mode === 'cricket' ? (
          <CricketScores game={game} />
        ) : (
          <TrainingScores game={game} />
        )}
      </section>

      <section className={`card ${styles.turn}`} aria-live="polite">
        <div className={styles.turnHeader}>
          <span className={styles.dot} style={{ background: current.color }} />
          <strong>{current.name}</strong>
          {(game.mode === 'x01' || game.mode === 'checkout_training' || game.mode === 'checkout_121') && game.checkout && !game.awaiting_next && (
            <span className={styles.checkout}>
              {t('play.checkout')}: {game.checkout.join(' · ')}
            </span>
          )}
          <span className={styles.detection}>
            <DetectionBadge />
          </span>
        </div>
        <div className={styles.slots}>
          {[0, 1, 2].map((i) => {
            const label = shownDarts[i]
            // empty fields show the rest of the checkout route in green
            const suggestion =
              !label && !game.awaiting_next && game.checkout ? game.checkout[i - shownDarts.length] : undefined
            return (
              <button
                key={i}
                className={`${styles.slot} ${correcting === i ? styles.slotSelected : ''}`}
                disabled={!label || busy}
                onClick={() => setCorrecting(correcting === i ? null : i)}
                aria-label={label ? t('play.correctDart', { n: i + 1 }) : undefined}
              >
                {suggestion ? (
                  <span className={`${styles.slotLabel} ${styles.slotSuggestion}`} title={t('play.checkout')}>
                    {suggestion}
                  </span>
                ) : (
                  <span className={styles.slotLabel}>{label ?? '–'}</span>
                )}
                {label && game.turn_sources[i] === 'auto' && (
                  (game.turn_confidence[i] ?? 1) < LOW_CONFIDENCE ? (
                    <span className={styles.unsure} title={t('play.unsure')}>
                      ?
                    </span>
                  ) : (
                    <span className={styles.auto} title={t('play.detected')}>
                      ◉
                    </span>
                  )
                )}
                {label && (game.mode === 'x01' || game.mode === 'checkout_training' || game.mode === 'checkout_121') && (
                  <span className={styles.slotPoints}>{dartPoints(label)}</span>
                )}
              </button>
            )
          })}
          <div className={styles.turnTotal}>
            {turn?.bust && showTurn ? (
              <span className={styles.bust}>{t('play.bust')}</span>
            ) : (
              <span>{showTurn && turn ? turn.values.reduce((a, b) => a + b, 0) : 0}</span>
            )}
          </div>
        </div>
        {correcting !== null && <p className={styles.hint}>{t('play.correctHint', { n: correcting + 1 })}</p>}
        {legWinner && <p className={styles.legWon}>{t('play.legWon', { name: legWinner.name })}</p>}
        {game.awaiting_next && !legWinner && <p className={styles.hint}>{t('play.pullDarts')}</p>}
      </section>

      <section className={`card ${styles.input}`}>
        <div className={styles.inputTabs} role="tablist">
          {(['pad', 'board'] as InputMode[]).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={inputMode === m}
              className={inputMode === m ? styles.tabActive : styles.tab}
              onClick={() => setInputMode(m)}
            >
              {t(`play.input.${m}`)}
            </button>
          ))}
        </div>
        {inputMode === 'pad' ? (
          <Pad
            multiplier={multiplier}
            setMultiplier={setMultiplier}
            onDart={(l) => void enter(l)}
            onBounce={shownDarts.length > 0 ? () => void bounce() : undefined}
            disabled={false}
          />
        ) : (
          <div className={styles.boardInput}>
            <DartBoard darts={shownDarts} selected={correcting} onSelect={(l) => void enter(l)} />
          </div>
        )}
        <div className={styles.actions}>
          <button className="button" onClick={() => void undo()} disabled={busy}>
            ↶ {t('play.undo')}
          </button>
          <button className="button primary" onClick={() => void next()} disabled={busy}>
            {game.awaiting_next ? t('play.nextPlayer') : t('play.endTurn')}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      <History game={game} />
      <GameMenu displayMode={displayMode} onDisplayMode={toggleDisplayMode} />
    </div>
  )
}

function MatchInfo({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const s = game.settings
  const title =
    game.mode === 'x01'
      ? `${s.start_score} · ${t(`newGame.rule.${s.in_rule as InOutRule}`)} in · ${t(`newGame.rule.${s.out_rule as InOutRule}`)} out`
      : game.mode === 'cricket'
        ? `Cricket · ${t(`newGame.variants.${s.variant as CricketVariant}`)}`
        : `${t(`modes.${game.mode}`)}${game.round && game.rounds ? ` · ${t('play.round', { round: game.round, rounds: game.rounds })}` : ''}`
  const legs = Number(s.legs_to_win)
  const sets = Number(s.sets_to_win)
  const [rules, setRules] = useState(false)
  return (
    <>
      <p className={styles.matchInfo}>
        {title}
        {(legs > 1 || sets > 1) && (
          <>
            {' · '}
            {sets > 1 && `${t('play.set')} ${game.set} · `}
            {t('play.leg')} {game.leg} · {t('play.firstTo', { count: legs })}
          </>
        )}{' '}
        <RulesButton mode={game.mode} onOpen={() => setRules(true)} />
      </p>
      {rules && <RulesDialog mode={game.mode} onClose={() => setRules(false)} />}
    </>
  )
}

function PlayerHeader({ game, player }: { game: GameState; player: GamePlayer }) {
  const sets = Number(game.settings.sets_to_win) > 1
  const legs = Number(game.settings.legs_to_win) > 1 || sets
  return (
    <div className={styles.playerHeader}>
      {player.avatar ? (
        <Avatar name={player.name} color={player.color} avatar={player.avatar} size={40} />
      ) : (
        <span className={styles.dot} style={{ background: player.color }} />
      )}
      <span className={styles.playerName}>
        {player.bot_level ? '🤖 ' : ''}
        {player.name}
      </span>
      {legs && (
        <span className={styles.legs}>
          {sets && `${game.sets_won[player.position]} · `}
          {game.legs_won[player.position]}
        </span>
      )}
    </div>
  )
}

function X01Scores({ game }: { game: GameState }) {
  const { t } = useTranslation()
  return (
    <div className={styles.playerGrid} data-count={game.players.length}>
      {game.players.map((p) => {
        const active = p.position === game.current_player
        // last completed turn (the running one is shown separately)
        const own = game.history.filter((h) => h.player === p.position)
        const running = game.turn && !game.turn.closed && game.turn.player === p.position
        const last = running ? own.at(-2) : own.at(-1)
        return (
          <article key={p.position} className={`card ${styles.player} ${active ? styles.active : ''}`}>
            <PlayerHeader game={game} player={p} />
            <div className={styles.remaining}>{game.remaining?.[p.position]}</div>
            <div className={styles.playerStats}>
              <span>
                Ø {p.stats.average?.toFixed(1) ?? '–'}
              </span>
              <span>
                {t('play.last')}: {last ? (last.bust ? t('play.bust') : last.total) : '–'}
              </span>
              <span>
                {t('play.darts')}: {p.stats.darts}
              </span>
            </div>
          </article>
        )
      })}
    </div>
  )
}

const MARK_SYMBOLS = ['', '/', '✕', 'Ⓧ']

function CricketScores({ game }: { game: GameState }) {
  const targets = game.targets ?? []
  const marks = game.marks ?? []
  return (
    <div className={`card ${styles.cricket}`}>
      <table>
        <thead>
          <tr>
            <th />
            {game.players.map((p) => (
              <th key={p.position} className={p.position === game.current_player ? styles.activeCol : undefined}>
                <PlayerHeader game={game} player={p} />
                <div className={styles.cricketPoints}>{game.points?.[p.position]}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {targets.map((target, ti) => {
            const closedByAll = marks.every((m) => m[ti] >= 3)
            return (
              <tr key={target} className={closedByAll ? styles.closedRow : undefined}>
                <th scope="row">{target === 25 ? 'B' : target}</th>
                {game.players.map((p) => (
                  <td key={p.position} className={p.position === game.current_player ? styles.activeCol : undefined}>
                    <span className={marks[p.position][ti] >= 3 ? styles.markClosed : styles.mark}>
                      {MARK_SYMBOLS[marks[p.position][ti]]}
                    </span>
                  </td>
                ))}
              </tr>
            )
          })}
          <tr>
            <th scope="row">MPR</th>
            {game.players.map((p) => (
              <td key={p.position} className={styles.mpr}>
                {p.stats.mpr?.toFixed(2) ?? '–'}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

/** The field to aim at in training modes, as large as the scores (Halve-It etc.). */
function TargetBanner({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const targetText = useTargetText()
  const target = trainingTarget(game)
  if (!target || game.finished) return null
  const player = game.players[game.current_player]
  return (
    <div className={styles.targetBanner} aria-live="polite">
      <span className={styles.targetLabel}>
        {t('play.target')}
        {game.player_count > 1 && <span className="muted"> · {player.name}</span>}
      </span>
      <strong className={styles.targetValue}>{targetText(target)}</strong>
      {game.round && game.rounds ? (
        <span className={styles.targetRound}>{t('play.roundOf', { round: game.round, total: game.rounds })}</span>
      ) : null}
    </div>
  )
}

function TrainingScores({ game }: { game: GameState }) {
  const { t } = useTranslation()
  return (
    <div className={styles.playerGrid} data-count={game.players.length}>
      {game.players.map((p) => {
        const i = p.position
        const active = i === game.current_player
        let big: string | number = '–'
        let detail = ''
        switch (game.mode) {
          case 'around_the_clock':
            big = game.current_targets?.[i] ?? '✓'
            detail = t('play.progress', { done: game.position?.[i] ?? 0, total: game.targets?.length ?? 0 })
            break
          case 'shanghai':
          case 'bobs_27':
            big = game.scores?.[i] ?? 0
            detail = game.out?.[i] ? t('play.out') : t('play.points')
            break
          case 'checkout_training': {
            const index = game.target_index?.[i] ?? 0
            const total = game.targets?.length ?? 0
            big = index < total ? (game.remaining?.[i] ?? '–') : '✓'
            detail = t('play.checkoutProgress', {
              done: game.successes?.[i] ?? 0,
              target: Math.min(index + 1, total),
              total,
            })
            break
          }
          case 'doubles_training':
            big = game.hits?.[i] ?? 0
            detail = t('play.hits')
            break
          case 'segment_training':
            big = game.hits?.[i] ?? 0
            detail = t('play.segmentProgress', { darts: game.darts_thrown?.[i] ?? 0, hits: game.hits?.[i] ?? 0, limit: game.limit ?? 0, context: game.end })
            break
          case 'checkout_121':
            big = game.remaining?.[i] ?? '–'
            detail = t('play.checkout121', {
              target: game.target_score?.[i] ?? 0,
              attempt: game.attempt?.[i] ?? 1,
              attempts: game.attempts ?? 0,
              best: game.best?.[i] || '–',
            })
            break
          case 'score_training':
          case 'halve_it':
            big = game.scores?.[i] ?? 0
            detail = t('play.roundOf', { round: game.round ?? 1, total: game.rounds ?? 0 })
            break
          case 'gotcha':
            big = game.scores?.[i] ?? 0
            detail = t('play.goal', { goal: game.goal ?? 0 })
            break
          case 'killer': {
            const lives = game.lives?.[i] ?? 0
            big = lives > 0 ? '♥'.repeat(lives) : '✗'
            detail = `${game.numbers?.[i] ?? ''} · ${game.killer?.[i] ? t('play.killer') : t('play.notKiller')}`
            break
          }
          case 'bull_off': {
            const own = game.history.filter((h) => h.player === i)
            big = own.at(-1)?.darts[0] ?? '–'
            detail = t('play.bullOffRound', { round: Math.max(own.length, 1) })
            break
          }
        }
        return (
          <article key={i} className={`card ${styles.player} ${active ? styles.active : ''}`}>
            <PlayerHeader game={game} player={p} />
            <div className={styles.remaining}>{big}</div>
            <div className={styles.playerStats}>
              <span>{detail}</span>
              <span>
                {t('play.darts')}: {p.stats.darts}
              </span>
            </div>
          </article>
        )
      })}
    </div>
  )
}

function Pad({
  multiplier,
  setMultiplier,
  onDart,
  onBounce,
  disabled,
}: {
  multiplier: 1 | 2 | 3
  setMultiplier: (m: 1 | 2 | 3) => void
  onDart: (label: string) => void
  onBounce?: () => void
  disabled: boolean
}) {
  const { t } = useTranslation()
  const numbers = Array.from({ length: 20 }, (_, i) => i + 1)
  return (
    <div className={styles.pad}>
      <div className={styles.multipliers}>
        {([1, 2, 3] as const).map((m) => (
          <button
            key={m}
            className={multiplier === m ? styles.multiplierActive : styles.multiplier}
            aria-pressed={multiplier === m}
            onClick={() => setMultiplier(multiplier === m && m !== 1 ? 1 : m)}
          >
            {t(`play.multiplier.${m}`)}
          </button>
        ))}
      </div>
      <div className={styles.numbers}>
        {numbers.map((n) => (
          <button key={n} disabled={disabled} onClick={() => onDart(dartLabel(n, multiplier))}>
            {n}
          </button>
        ))}
        <button disabled={disabled} onClick={() => onDart('25')}>
          25
        </button>
        <button disabled={disabled} onClick={() => onDart('BULL')}>
          Bull
        </button>
        <button disabled={disabled} className={styles.miss} onClick={() => onDart('MISS')}>
          {t('play.miss')}
        </button>
        <button
          disabled={disabled || !onBounce}
          className={styles.bounce}
          onClick={onBounce}
          title={t('play.bounceHint')}
        >
          {t('play.bounce')}
        </button>
      </div>
    </div>
  )
}

function History({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const { setGame } = useLiveGame()
  const [photos, setPhotos] = useState<VisitRef | null>(null)
  const turns = [...game.history].reverse().slice(0, 12)
  if (turns.length === 0) return null
  return (
    <section className={`card ${styles.history}`}>
      <h2 className="cardTitle">{t('play.history')}</h2>
      <ol>
        {turns.map((turn, i) => {
          const player = game.players[turn.player]
          const turnIndex = game.history.length - 1 - i
          return (
            <li key={turnIndex}>
              <span className={styles.dot} style={{ background: player.color }} />
              <span className={styles.historyName}>{player.name}</span>
              <span className={styles.historyDarts}>{turn.darts.join(' ')}</span>
              <span className={turn.bust ? styles.bust : styles.historyTotal}>
                {turn.bust ? t('play.bust') : turn.total}
              </span>
              <button
                className={styles.photoButton}
                title={t('photos.show')}
                aria-label={t('photos.show')}
                onClick={() => setPhotos({ ...game.history_leg, turn_index: turnIndex })}
              >
                📷
              </button>
            </li>
          )
        })}
      </ol>
      {photos && (
        <VisitPhotos
          gameId={game.id}
          initial={photos}
          playerNames={game.players.map((p) => p.name)}
          onClose={() => setPhotos(null)}
          onCorrected={setGame}
        />
      )}
    </section>
  )
}

function GameMenu({ displayMode, onDisplayMode }: { displayMode: boolean; onDisplayMode: () => void }) {
  const { t } = useTranslation()
  const { setGame } = useLiveGame()
  const navigate = useNavigate()
  const abort = async () => {
    if (!window.confirm(t('play.confirmAbort'))) return
    await sendJson('POST', '/api/games/active/abort')
    setGame(null)
    void navigate('/')
  }
  return (
    <div className={styles.menu}>
      <button className="button" onClick={onDisplayMode} aria-pressed={displayMode} title={t('play.displayModeHint')}>
        {displayMode ? t('play.displayModeOff') : t('play.displayModeOn')}
      </button>
      <button className="button danger" onClick={() => void abort()}>
        {t('play.abort')}
      </button>
    </div>
  )
}

function readPending(): PendingGame | null {
  try {
    return JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? 'null') as PendingGame | null
  } catch {
    return null
  }
}

/** After the bull-off: start the prepared game with the winner throwing first. */
function BullOffResult({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const { setGame } = useLiveGame()
  const navigate = useNavigate()
  const winner = game.winner !== null ? game.players[game.winner] : null
  const pending = readPending()

  const startGame = async () => {
    if (!pending || game.winner === null) return
    // keep the order around the table, starting with the winner
    const order = [...pending.players.slice(game.winner), ...pending.players.slice(0, game.winner)]
    const state = await sendJson<GameState>('POST', '/api/games', { ...pending, players: order })
    sessionStorage.removeItem(PENDING_KEY)
    setGame(state)
  }

  return (
    <div className={styles.finished}>
      {winner && (
        <div className={styles.winner}>
          <span className={styles.winnerDot} style={{ background: winner.color }} />
          <h1>{t('play.startsFirst', { name: winner.name })}</h1>
        </div>
      )}
      <div className={styles.actions}>
        {pending ? (
          <button className="button primary large" onClick={() => void startGame()}>
            {t('play.startPrepared', { mode: t(`modes.${pending.mode}`) })}
          </button>
        ) : (
          <button className="button primary large" onClick={() => void navigate('/play/new')}>
            {t('home.newGame')}
          </button>
        )}
      </div>
    </div>
  )
}

function Finished({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const { setGame } = useLiveGame()
  const navigate = useNavigate()
  const winner = game.winner !== null ? game.players[game.winner] : null
  const x01 = game.mode === 'x01'

  const errorText = useErrorText()
  const [error, setError] = useState<string | null>(null)
  const rematch = async () => {
    setGame(await sendJson<GameState>('POST', '/api/games/rematch'))
  }

  // continue the match with a higher target: one more set if sets are played, else one more leg
  const canPlayOn = game.mode === 'x01' || game.mode === 'cricket'
  const legs = Number(game.settings.legs_to_win ?? 1)
  const sets = Number(game.settings.sets_to_win ?? 1)
  const next = sets > 1 ? { legs_to_win: legs, sets_to_win: sets + 1 } : { legs_to_win: legs + 1, sets_to_win: sets }
  const playOn = async () => {
    setError(null)
    try {
      setGame(await sendJson<GameState>('POST', '/api/games/play-on', next))
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <div className={styles.finished}>
      {winner && (
        <div className={styles.winner}>
          <span className={styles.winnerDot} style={{ background: winner.color }} />
          <h1>{t('play.winner', { name: winner.name })}</h1>
        </div>
      )}
      <div className={`card ${styles.statsTable}`}>
        <table>
          <thead>
            <tr>
              <th />
              {game.players.map((p) => (
                <th key={p.position}>{p.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(!x01 && game.mode !== 'cricket'
              ? ([
                  ['play.stats.score', (p: GamePlayer) => p.stats.score ?? '–'],
                  ['play.stats.hits', (p: GamePlayer) => p.stats.hits],
                  [
                    'play.stats.hitRate',
                    (p: GamePlayer) => (p.stats.hit_rate === null ? '–' : `${Math.round(p.stats.hit_rate * 100)} %`),
                  ],
                  ['play.stats.darts', (p: GamePlayer) => p.stats.darts],
                ] as const)
              : x01
              ? ([
                  ['play.stats.legs', (p: GamePlayer) => p.stats.legs_won],
                  ['play.stats.average', (p: GamePlayer) => p.stats.average?.toFixed(2) ?? '–'],
                  ['play.stats.first9', (p: GamePlayer) => p.stats.first9_average?.toFixed(2) ?? '–'],
                  [
                    'play.stats.checkout',
                    (p: GamePlayer) =>
                      p.stats.checkout_rate === null
                        ? '–'
                        : `${Math.round(p.stats.checkout_rate * 100)} % (${p.stats.checkouts}/${p.stats.checkout_attempts})`,
                  ],
                  ['play.stats.highestFinish', (p: GamePlayer) => p.stats.highest_finish || '–'],
                  ['play.stats.bestLeg', (p: GamePlayer) => p.stats.best_leg_darts ?? '–'],
                  ['play.stats.tons', (p: GamePlayer) => `${p.stats.tons['100']} / ${p.stats.tons['140']} / ${p.stats.tons['180']}`],
                  ['play.stats.darts', (p: GamePlayer) => p.stats.darts],
                ] as const)
              : ([
                  ['play.stats.legs', (p: GamePlayer) => p.stats.legs_won],
                  ['play.stats.mpr', (p: GamePlayer) => p.stats.mpr?.toFixed(2) ?? '–'],
                  ['play.stats.marks', (p: GamePlayer) => p.stats.marks],
                  ['play.stats.darts', (p: GamePlayer) => p.stats.darts],
                ] as const)
            ).map(([key, value]) => (
              <tr key={key}>
                <th scope="row">{t(key)}</th>
                {game.players.map((p) => (
                  <td key={p.position}>{value(p)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.actions}>
        <button className="button primary large" onClick={() => void rematch()}>
          {t('play.rematch')}
        </button>
        {canPlayOn && (
          <button className="button large" onClick={() => void playOn()}>
            {sets > 1
              ? t('play.playOnSets', { count: next.sets_to_win })
              : t('play.playOnLegs', { count: next.legs_to_win })}
          </button>
        )}
        <Link to="/play/new" className="button large">
          {t('home.newGame')}
        </Link>
        <button className="button large" onClick={() => void navigate('/')}>
          {t('nav.home')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
