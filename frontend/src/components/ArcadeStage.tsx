import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from '../api'
import { R, SEGMENT_DEG, SEGMENTS, scoreAt } from '../dart'
import Avatar from './Avatar'
import styles from './ArcadeStage.module.css'

export type Monster = { id: number; kind: string; x: number; y: number; radius: number; value: number; alive: boolean }
type Effect = { player: number; killed: number[]; points: number; grew: boolean; position: [number, number] | null }
type Popup = { key: number; x: number; y: number; text: string; good: boolean }

const VIEW = 200 // mm shown around the bull (the board ends at 170)

/** Monster hunt: the dartboard is the game world. Monsters sit where they sit on the real
 *  board, darts are drawn where they landed; tapping the board throws a dart there. */
export default function ArcadeStage({
  game,
  onTap,
  disabled,
}: {
  game: GameState
  onTap?: (label: string, x: number, y: number) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const svg = useRef<SVGSVGElement>(null)
  const monsters = (game.monsters ?? []) as Monster[]
  const darts = game.arcade_darts ?? []
  const effect = game.last_effect as Effect | null | undefined
  const [popups, setPopups] = useState<Popup[]>([])
  const [intro, setIntro] = useState<{ key: string; round: number; name: string } | null>(null)
  const lastEvent = useRef(game.event_count)

  // "+100" pop-ups where the dart hit
  useEffect(() => {
    if (game.event_count <= lastEvent.current) {
      lastEvent.current = game.event_count
      return
    }
    lastEvent.current = game.event_count
    if (!effect?.position) return
    const [x, y] = effect.position
    const popup: Popup = {
      key: game.event_count,
      x,
      y,
      text: effect.points ? `+${effect.points}` : t('arcade.grow'),
      good: effect.points > 0,
    }
    setPopups((list) => [...list.slice(-4), popup])
    const timer = window.setTimeout(() => setPopups((list) => list.filter((p) => p.key !== popup.key)), 1400)
    return () => window.clearTimeout(timer)
  }, [game.event_count, effect, t])

  // "Round 3 - Alex" between turns
  const player = game.players[game.current_player]
  const introKey = `${game.id}-${game.round}-${game.current_player}`
  useEffect(() => {
    if (game.finished || game.awaiting_next || darts.length > 0) return
    setIntro({ key: introKey, round: game.round ?? 1, name: player.name })
    const timer = window.setTimeout(() => setIntro(null), 1800)
    return () => window.clearTimeout(timer)
    // only when a new turn begins
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [introKey])

  const tap = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onTap || disabled || !svg.current) return
    const point = svg.current.createSVGPoint()
    point.x = e.clientX
    point.y = e.clientY
    const matrix = svg.current.getScreenCTM()
    if (!matrix) return
    const p = point.matrixTransform(matrix.inverse())
    const x = p.x
    const y = -p.y
    onTap(scoreAt(x, y), Math.round(x * 10) / 10, Math.round(y * 10) / 10)
  }

  const alive = monsters.filter((m) => m.alive).length
  const banner = game.awaiting_next
    ? t('play.pullDarts')
    : effect && darts.length > 0
      ? effect.killed.length > 1
        ? t('arcade.multiKill', { count: effect.killed.length })
        : effect.killed.length === 1
          ? t('arcade.hit', { points: effect.points })
          : t('arcade.missed')
      : game.double_round
        ? t('arcade.doubleRound')
        : t('arcade.instruction', { count: alive })

  return (
    <div className={styles.stage}>
      <div className={styles.header}>
        <span className={styles.round}>
          {Array.from({ length: game.rounds ?? 0 }, (_, i) => (
            <span key={i} className={i + 1 < (game.round ?? 1) ? styles.roundDone : i + 1 === game.round ? styles.roundNow : styles.roundOpen} />
          ))}
        </span>
        <span className={styles.roundText}>
          {t('play.roundOf', { round: game.round ?? 1, total: game.rounds ?? 0 })}
          {game.double_round && <strong className={styles.double}> ×2</strong>}
        </span>
      </div>

      <div className={styles.world}>
        <aside className={styles.players}>
          {game.players.map((p) => (
            <div key={p.position} className={`${styles.card} ${p.position === game.current_player ? styles.cardActive : ''}`}>
              <Avatar name={p.name} color={p.color} avatar={p.avatar} size={44} />
              <span className={styles.cardName}>{p.name}</span>
              <span className={styles.cardScore}>{game.scores?.[p.position] ?? 0}</span>
            </div>
          ))}
        </aside>

        <svg
          ref={svg}
          className={`${styles.board} ${onTap && !disabled ? styles.tappable : ''}`}
          viewBox={`${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`}
          onClick={tap}
          role="img"
          aria-label={t('arcade.board')}
        >
          <defs>
            <radialGradient id="arcadeGlow">
              <stop offset="0%" stopColor="#1f3b2a" />
              <stop offset="100%" stopColor="#0b120e" />
            </radialGradient>
          </defs>
          <circle r={VIEW} fill="url(#arcadeGlow)" />
          {/* the board, drawn muted so the monsters stand out */}
          <circle r={R.doubleOuter} className={styles.boardFace} />
          {[R.doubleInner, R.tripleOuter, R.tripleInner, R.outerBull].map((r) => (
            <circle key={r} r={r} className={styles.ring} />
          ))}
          <circle r={R.bull} className={styles.bull} />
          {SEGMENTS.map((n, i) => {
            const a = ((90 - i * SEGMENT_DEG - SEGMENT_DEG / 2) * Math.PI) / 180
            const c = ((90 - i * SEGMENT_DEG) * Math.PI) / 180
            return (
              <g key={n}>
                <line
                  x1={R.outerBull * Math.cos(a)}
                  y1={-R.outerBull * Math.sin(a)}
                  x2={R.doubleOuter * Math.cos(a)}
                  y2={-R.doubleOuter * Math.sin(a)}
                  className={styles.wire}
                />
                <text x={186 * Math.cos(c)} y={-186 * Math.sin(c)} className={styles.number}>
                  {n}
                </text>
              </g>
            )
          })}

          {monsters.map((m) => (
            <g
              key={`${introKey}-${m.id}`}
              className={m.alive ? styles.monster : styles.monsterGone}
              style={{ transform: `translate(${m.x}px, ${-m.y}px)` }}
            >
              <circle r={m.radius} className={styles.hitArea} />
              <g className={styles.bob} style={{ animationDelay: `${(m.id * 0.37) % 1.5}s` }}>
                <image
                  href={`/arcade/monsters/${m.kind}.svg`}
                  x={-m.radius * 1.25}
                  y={-m.radius * 1.25}
                  width={m.radius * 2.5}
                  height={m.radius * 2.5}
                />
              </g>
              {m.alive && (
                <text y={m.radius * 1.25 + 9} className={styles.value}>
                  {m.value}
                </text>
              )}
            </g>
          ))}

          {darts.map((d, i) =>
            d.position ? (
              <g key={i} style={{ transform: `translate(${d.position[0]}px, ${-d.position[1]}px)` }}>
                <g className={styles.dart}>
                  <circle r={4.5} />
                  <circle r={1.6} className={styles.dartTip} />
                </g>
              </g>
            ) : null,
          )}

          {popups.map((p) => (
            <text key={p.key} x={p.x} y={-p.y - 10} className={p.good ? styles.popup : styles.popupBad}>
              {p.text}
            </text>
          ))}
        </svg>
      </div>

      <div className={styles.banner}>{banner}</div>

      {intro && (
        <div key={intro.key} className={styles.intro}>
          <span>{t('play.roundOf', { round: intro.round, total: game.rounds ?? 0 })}</span>
          <strong>{t('arcade.yourTurn', { name: intro.name })}</strong>
        </div>
      )}
    </div>
  )
}
