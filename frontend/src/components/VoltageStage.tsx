import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { GameState, InOutRule } from '../api'
import { R, SEGMENT_DEG, SEGMENTS, dartCenter, dartPoints } from '../dart'
import Avatar from './Avatar'
import VoltageSky, { type Strike } from './VoltageSky'
import styles from './VoltageStage.module.css'

const VIEW = 190
const RAYS = Array.from({ length: 10 }, (_, i) => (i * Math.PI * 2) / 10)

/** X01 "Voltage" skin, full screen: every player is a battery that drains with the remaining
 *  score; darts glow on a neon board and are struck by lightning, big visits send storms
 *  through the battery. `children` go into the bottom toolbar; tapping a dart of the running
 *  turn calls `onCorrect`. */
export default function VoltageStage({
  game,
  onCorrect,
  children,
}: {
  game: GameState
  onCorrect: (dart: number) => void
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const [zap, setZap] = useState<{ key: number; player: number; big: boolean } | null>(null)
  const [strike, setStrike] = useState<Strike | null>(null)
  const [fullscreen, setFullscreen] = useState(() => !!document.fullscreenElement)
  const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  useEffect(() => {
    const update = () => setFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', update)
    return () => document.removeEventListener('fullscreenchange', update)
  }, [])
  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
    else void document.documentElement.requestFullscreen?.().catch(() => undefined)
  }

  const turn = game.turn
  const showTurn = turn && (turn.player === game.current_player || game.awaiting_next)
  const darts = showTurn ? turn.darts : []

  // a strike on every new dart, lightning for 100+ visits, a storm for a 180, a short on bust
  const closed = Boolean(showTurn && turn?.closed)
  const seen = useRef({ darts: darts.length, event: game.event_count, awaiting: game.awaiting_next, closed })
  useEffect(() => {
    const before = seen.current
    seen.current = { darts: darts.length, event: game.event_count, awaiting: game.awaiting_next, closed }
    if (before.event === game.event_count) return
    // the first dart of a new turn replaces the full previous one
    const newTurn = before.awaiting && !game.awaiting_next && darts.length === 1
    if (darts.length > before.darts || newTurn) setStrike({ key: game.event_count, kind: 'dart' })
    // only when the visit has just been completed (not again on "next player" or undo)
    if (!turn || !closed || before.closed) return
    if (turn.bust) {
      setStrike({ key: game.event_count + 0.5, kind: 'bust', player: turn.player })
      return
    }
    const total = turn.values.reduce((a, b) => a + b, 0)
    if (total < 100) return
    const big = total === 180
    window.setTimeout(() => setStrike({ key: game.event_count + 0.5, kind: big ? 'storm' : 'ton', player: turn.player }), 250)
    setZap({ key: game.event_count, player: turn.player, big })
    const timer = window.setTimeout(() => setZap(null), 1600)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.event_count])

  const positions = game.turn_positions ?? []
  const s = game.settings
  const starts = (s.start_scores as unknown as (number | null)[] | undefined) ?? []
  const start = (p: number) => starts[p] || Number(s.start_score)
  const sets = Number(s.sets_to_win) > 1
  const legs = Number(s.legs_to_win) > 1 || sets
  const showRoute = game.checkout && !game.awaiting_next
  // the checkout as a lightning trail from the last dart through the fields to finish on
  const route = showRoute
    ? ((game.checkout ?? []).map(dartCenter).filter(Boolean) as [number, number][])
    : []
  const half = Math.ceil(game.players.length / 2)
  const left = game.players.slice(0, half)
  const right = game.players.slice(half)
  const total = showTurn && turn ? turn.values.reduce((a, b) => a + b, 0) : 0

  const battery = (p: GameState['players'][number]) => {
    const remaining = game.remaining?.[p.position] ?? start(p.position)
    const level = Math.max(0, Math.min(1, remaining / start(p.position)))
    const tone = level > 0.5 ? styles.high : level > 0.2 ? styles.mid : styles.low
    const active = p.position === game.current_player
    const shorted = turn?.closed && turn.bust && turn.player === p.position && showTurn
    return (
      <div key={p.position} className={`${styles.battery} ${active ? styles.active : ''} ${shorted ? styles.shorted : ''}`}>
        <div className={styles.who}>
          <Avatar name={p.name} color={p.color} avatar={p.avatar} size={40} />
          <span className={styles.name}>{p.name}</span>
          {legs && (
            <span className={styles.legs}>
              {sets && `${game.sets_won[p.position]} · `}
              {game.legs_won[p.position]}
            </span>
          )}
        </div>
        <div className={styles.cell} data-volt={active ? 'active' : undefined} data-volt-player={p.position}>
          <div className={`${styles.charge} ${tone}`} style={{ height: `${level * 100}%` }} />
          <span className={styles.remaining}>{remaining}</span>
          {zap && zap.player === p.position && (
            <img key={zap.key} src="/arcade/bolt.webp" alt="" className={zap.big ? styles.boltBig : styles.bolt} />
          )}
        </div>
        <span className={styles.avg}>Ø {p.stats.average?.toFixed(1) ?? '–'}</span>
      </div>
    )
  }

  return (
    <div className={styles.stage}>
      <div className={styles.backdrop} aria-hidden />
      <div className={styles.floor} aria-hidden />
      {!reducedMotion && <VoltageSky strike={strike} />}
      {zap?.big && <div key={`flash-${zap.key}`} className={styles.flash} />}

      <header className={styles.hud}>
        <div className={styles.match}>
          <span>
            {s.start_score} · {t(`newGame.rule.${s.in_rule as InOutRule}`)} in · {t(`newGame.rule.${s.out_rule as InOutRule}`)} out
          </span>
          {legs && (
            <span className={styles.matchSub}>
              {sets && `${t('play.set')} ${game.set} · `}
              {t('play.leg')} {game.leg} · {t('play.firstTo', { count: Number(s.legs_to_win) })}
            </span>
          )}
        </div>
        <div className={styles.slots}>
          {[0, 1, 2].map((i) => {
            const label = darts[i]
            const suggestion = !label && showRoute ? game.checkout?.[i - darts.length] : undefined
            return (
              <button
                key={i}
                className={`${styles.slot} ${label ? styles.slotFilled : ''} ${suggestion ? styles.slotRoute : ''}`}
                disabled={!label}
                onClick={() => onCorrect(i)}
                aria-label={label ? t('play.correctDart', { n: i + 1 }) : undefined}
              >
                <span>{label ?? suggestion ?? '–'}</span>
                {label && <small>{dartPoints(label)}</small>}
              </button>
            )
          })}
          <div className={`${styles.total} ${turn?.bust && showTurn ? styles.totalBust : ''}`}>
            {turn?.bust && showTurn ? t('play.bust') : total}
          </div>
        </div>
        <div className={styles.corner}>
          <button className={styles.icon} onClick={toggleFullscreen} aria-pressed={fullscreen} title={t('voltage.fullscreen')}>
            ⛶
          </button>
          <Link to="/" className={styles.icon} title={t('voltage.home')} aria-label={t('voltage.home')}>
            ⌂
          </Link>
        </div>
      </header>

      <div className={styles.arena}>
        <div className={styles.side} style={{ '--rows': left.length } as CSSProperties}>
          {left.map(battery)}
        </div>
        <div className={styles.center}>
          <div className={styles.boardWrap}>
          {/* the pulses are separate layers animated with transform/opacity only, so the
              blurred board itself is rasterized once instead of every frame */}
          <div className={styles.pulse} aria-hidden />
          <div className={`${styles.pulse} ${styles.pulseLate}`} aria-hidden />
          <svg className={styles.board} viewBox={`${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`} role="img" aria-label={t('voltage.board')}>
            <defs>
              <filter id="voltGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="2.2" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <circle r={R.doubleOuter + 12} className={styles.plate} />
            <g filter="url(#voltGlow)">
              {[R.doubleOuter, R.doubleInner, R.tripleOuter, R.tripleInner, R.outerBull].map((r) => (
                <circle key={r} r={r} className={r === R.doubleOuter || r === R.tripleOuter ? styles.ringStrong : styles.ring} />
              ))}
              <circle r={R.bull} className={styles.bull} />
              {SEGMENTS.map((n, i) => {
                const a = ((90 - i * SEGMENT_DEG - SEGMENT_DEG / 2) * Math.PI) / 180
                return (
                  <line
                    key={n}
                    x1={R.outerBull * Math.cos(a)}
                    y1={-R.outerBull * Math.sin(a)}
                    x2={R.doubleOuter * Math.cos(a)}
                    y2={-R.doubleOuter * Math.sin(a)}
                    className={styles.wire}
                  />
                )
              })}
            </g>
            {SEGMENTS.map((n, i) => {
              const c = ((90 - i * SEGMENT_DEG) * Math.PI) / 180
              return (
                <text key={n} x={180 * Math.cos(c)} y={-180 * Math.sin(c)} className={styles.number}>
                  {n}
                </text>
              )
            })}
            {route.length > 0 && (
              <g>
                <polyline points={route.map(([x, y]) => `${x},${-y}`).join(' ')} className={styles.trail} />
                {route.map(([x, y], i) => (
                  <circle key={i} cx={x} cy={-y} r={6} className={styles.trailStop} />
                ))}
              </g>
            )}
            {darts.map((label, i) => {
              // typed darts have no position: spread them a little so repeated fields stay visible
              const center = dartCenter(label)
              const at = positions[i] ?? (center && [center[0] + (i - 1) * 7, center[1] + (i % 2) * 4])
              if (!at) return null
              return (
                <g key={`${game.event_count}-${i}`} style={{ transform: `translate(${at[0]}px, ${-at[1]}px)` }}>
                  <g className={styles.rays}>
                    {RAYS.map((a) => (
                      <line key={a} x1={Math.cos(a) * 7} y1={Math.sin(a) * 7} x2={Math.cos(a) * 22} y2={Math.sin(a) * 22} />
                    ))}
                  </g>
                  <circle r={16} className={styles.shock} />
                  <g className={styles.dart} filter="url(#voltGlow)" data-volt="dart">
                    <circle r={5} />
                    <circle r={2} className={styles.dartCore} />
                  </g>
                </g>
              )
            })}
          </svg>
          </div>
        </div>
        <div className={styles.side} style={{ '--rows': Math.max(1, right.length) } as CSSProperties}>
          {right.map(battery)}
        </div>
      </div>

      <footer className={styles.toolbar}>{children}</footer>
    </div>
  )
}
