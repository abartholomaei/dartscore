import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from '../api'
import { R, SEGMENT_DEG, SEGMENTS } from '../dart'
import Avatar from './Avatar'
import styles from './ArcadeStage.module.css'
import { useBoardTap, VIEW } from './useBoardTap'

export type Monster = { id: number; kind: string; x: number; y: number; radius: number; value: number; alive: boolean }
type Effect = { player: number; killed: number[]; points: number; grew: boolean; position: [number, number] | null }
type Popup = { key: number; x: number; y: number; text: string; good: boolean }

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
  const board = useBoardTap(onTap, disabled)
  const monsters = (game.monsters ?? []) as Monster[]
  const darts = game.arcade_darts ?? []
  const effect = game.last_effect as Effect | null | undefined
  const [popups, setPopups] = useState<Popup[]>([])
  // the latest dart's effect, keyed by event number so the animation restarts every dart
  const [burst, setBurst] = useState<{ key: number; spots: [number, number][]; miss: [number, number] | null; grew: boolean; multi: boolean } | null>(null)
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
    const caught = monsters.filter((m) => effect.killed.includes(m.id)).map((m) => [m.x, m.y] as [number, number])
    setBurst({ key: game.event_count, spots: caught, miss: caught.length ? null : effect.position, grew: effect.grew, multi: caught.length > 1 })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.event_count, effect, t])

  // a new turn brings a new set of monsters
  const introKey = `${game.id}-${game.round}-${game.current_player}`
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
    <ArcadeShell game={game} banner={banner} dartsThrown={darts.length}>
      <svg {...board} aria-label={t('arcade.board')}>
        <defs>
          <clipPath id="arcadeClip">
            <circle r={VIEW - 1} />
          </clipPath>
          <radialGradient id="arcadeVignette">
            <stop offset="70%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.55" />
          </radialGradient>
        </defs>
        <g className={burst?.multi ? styles.pulse : undefined} key={burst?.multi ? burst.key : 'board'}>
          <image
            href="/arcade/monster-meadow.webp"
            x={-VIEW}
            y={-VIEW}
            width={2 * VIEW}
            height={2 * VIEW}
            clipPath="url(#arcadeClip)"
            preserveAspectRatio="xMidYMid slice"
          />
          <circle r={VIEW} fill="url(#arcadeVignette)" />
        </g>
        {/* the board lines, light and see-through over the meadow */}
        <BoardLines />

        {monsters.map((m) => (
          <g
            key={`${introKey}-${m.id}`}
            className={m.alive ? `${styles.monster} ${burst?.grew ? styles.wobble : ''}` : styles.monsterGone}
            style={{ transform: `translate(${m.x}px, ${-m.y}px)` }}
          >
            <circle r={m.radius} className={styles.hitArea} />
            <g className={styles.bob} style={{ animationDelay: `${(m.id * 0.37) % 1.5}s` }}>
              {/* animated sprite strip (4 frames of 256 px): idle loop, or the "caught" once */}
              <svg
                x={-m.radius * 1.75}
                y={-m.radius * 1.75}
                width={m.radius * 3.5}
                height={m.radius * 3.5}
                viewBox="0 0 256 256"
                overflow="hidden"
              >
                <clipPath id={`cell-${m.id}`}>
                  <rect width={256} height={256} />
                </clipPath>
                <g clipPath={`url(#cell-${m.id})`}>
                  <image
                    href={`/arcade/monsters/${m.kind}-${m.alive ? 'idle' : 'hurt'}.webp`}
                    width={1024}
                    height={256}
                    className={m.alive ? styles.stripLoop : styles.stripOnce}
                    style={{ animationDelay: m.alive ? `-${(m.id * 0.29) % 0.8}s` : undefined }}
                  />
                </g>
              </svg>
            </g>
            {m.alive && (
              <text y={m.radius * 1.6 + 8} className={styles.value}>
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

        {burst?.spots.map(([x, y], i) => (
          <image
            key={`${burst.key}-${i}`}
            href="/arcade/poof.webp"
            x={x - 26}
            y={-y - 26}
            width={52}
            height={52}
            className={styles.poof}
          />
        ))}
        {burst?.miss && (
          <g key={`dust-${burst.key}`} style={{ transform: `translate(${burst.miss[0]}px, ${-burst.miss[1]}px)` }}>
            <g className={styles.dust}>
              {[0, 60, 120, 180, 240, 300].map((a) => (
                <circle key={a} r={3} cx={Math.cos((a * Math.PI) / 180) * 6} cy={Math.sin((a * Math.PI) / 180) * 6} />
              ))}
            </g>
          </g>
        )}
        {popups.map((p) => (
          <text key={p.key} x={p.x} y={-p.y - 10} className={p.good ? styles.popup : styles.popupBad}>
            {p.text}
          </text>
        ))}
      </svg>
    </ArcadeShell>
  )
}

/** Board rings, wires and numbers, light and see-through over the painted world. */
export function BoardLines({ wires = true }: { wires?: boolean }) {
  return (
    <>
      {wires && <circle r={R.doubleOuter} className={styles.boardFace} />}
      {(wires ? [R.doubleInner, R.tripleOuter, R.tripleInner, R.outerBull] : [R.outerBull]).map((r) => (
        <circle key={r} r={r} className={styles.ring} />
      ))}
      <circle r={R.bull} className={styles.bull} />
      {SEGMENTS.map((n, i) => {
        const a = ((90 - i * SEGMENT_DEG - SEGMENT_DEG / 2) * Math.PI) / 180
        const c = ((90 - i * SEGMENT_DEG) * Math.PI) / 180
        return (
          <g key={n}>
            {wires && (
              <line
                x1={R.outerBull * Math.cos(a)}
                y1={-R.outerBull * Math.sin(a)}
                x2={R.doubleOuter * Math.cos(a)}
                y2={-R.doubleOuter * Math.sin(a)}
                className={styles.wire}
              />
            )}
            <text x={186 * Math.cos(c)} y={-186 * Math.sin(c)} className={styles.number}>
              {n}
            </text>
          </g>
        )
      })}
    </>
  )
}

/** The frame of every arcade game: round dots, player cards, the board, a banner and the
 *  "Round 3 - Alex" intro between turns. */
export function ArcadeShell({
  game,
  banner,
  dartsThrown,
  introLine,
  children,
}: {
  game: GameState
  banner: ReactNode
  dartsThrown: number
  introLine?: string
  children: ReactNode
}) {
  const { t } = useTranslation()
  const [intro, setIntro] = useState<{ key: string; round: number; name: string } | null>(null)
  const player = game.players[game.current_player]
  const introKey = `${game.id}-${game.round}-${game.current_player}`
  useEffect(() => {
    if (game.finished || game.awaiting_next || dartsThrown > 0) return
    setIntro({ key: introKey, round: game.round ?? 1, name: player.name })
    const timer = window.setTimeout(() => setIntro(null), 1800)
    return () => window.clearTimeout(timer)
    // only when a new turn begins
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [introKey])

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
        {children}
      </div>

      <div className={styles.banner}>{banner}</div>

      {intro && (
        <div key={intro.key} className={styles.intro}>
          <span>
            {t('play.roundOf', { round: intro.round, total: game.rounds ?? 0 })}
            {introLine && ` · ${introLine}`}
          </span>
          <strong>{t('arcade.yourTurn', { name: intro.name })}</strong>
        </div>
      )}
    </div>
  )
}
