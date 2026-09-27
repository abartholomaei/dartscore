import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from '../api'
import { R, SEGMENT_DEG, SEGMENTS, dartCenter } from '../dart'
import Avatar from './Avatar'
import styles from './VoltageStage.module.css'

const VIEW = 190

/** X01 "Voltage" skin: every player is a battery that drains with the remaining score; the
 *  darts glow on a neon board, big visits send lightning through the battery. */
export default function VoltageStage({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const [zap, setZap] = useState<{ key: number; player: number; big: boolean } | null>(null)

  // lightning for 100+ visits, a storm for a 180
  useEffect(() => {
    const turn = game.turn
    if (!turn?.closed || turn.bust) return
    const total = turn.values.reduce((a, b) => a + b, 0)
    if (total < 100) return
    setZap({ key: game.event_count, player: turn.player, big: total === 180 })
    const timer = window.setTimeout(() => setZap(null), 1600)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.event_count])

  const turn = game.turn
  const showTurn = turn && (turn.player === game.current_player || game.awaiting_next)
  const darts = showTurn ? turn.darts : []
  const positions = game.turn_positions ?? []
  const starts = (game.settings.start_scores as unknown as (number | null)[] | undefined) ?? []
  const start = (p: number) => starts[p] || Number(game.settings.start_score)
  const sets = Number(game.settings.sets_to_win) > 1
  const legs = Number(game.settings.legs_to_win) > 1 || sets
  const showRoute = game.checkout && !game.awaiting_next
  // the checkout as a lightning trail from the last dart through the fields to finish on
  const route = showRoute
    ? ((game.checkout ?? []).map(dartCenter).filter(Boolean) as [number, number][])
    : []
  const half = Math.ceil(game.players.length / 2)
  const left = game.players.slice(0, half)
  const right = game.players.slice(half)

  const battery = (p: GameState['players'][number]) => {
    const remaining = game.remaining?.[p.position] ?? start(p.position)
    const level = Math.max(0, Math.min(1, remaining / start(p.position)))
    const tone = level > 0.5 ? styles.high : level > 0.2 ? styles.mid : styles.low
    const active = p.position === game.current_player
    return (
      <div key={p.position} className={`${styles.battery} ${active ? styles.active : ''}`}>
        <div className={styles.who}>
          <Avatar name={p.name} color={p.color} avatar={p.avatar} size={34} />
          <span className={styles.name}>{p.name}</span>
          {legs && (
            <span className={styles.legs}>
              {sets && `${game.sets_won[p.position]} · `}
              {game.legs_won[p.position]}
            </span>
          )}
        </div>
        <div className={styles.cell}>
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
      {zap?.big && <div key={`flash-${zap.key}`} className={styles.flash} />}
      <div className={styles.side}>{left.map(battery)}</div>
      <div className={styles.center}>
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
            <g filter="url(#voltGlow)">
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
                <g className={styles.dart} filter="url(#voltGlow)">
                  <circle r={5} />
                  <circle r={2} className={styles.dartCore} />
                </g>
              </g>
            )
          })}
        </svg>
        {showRoute && (
          <div className={styles.route}>⚡ {(game.checkout ?? []).join(' · ')}</div>
        )}
      </div>
      <div className={styles.side}>{right.map(battery)}</div>
    </div>
  )
}
