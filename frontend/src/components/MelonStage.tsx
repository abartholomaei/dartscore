import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from '../api'
import { R } from '../dart'
import { ArcadeShell, BoardLines } from './ArcadeShell'
import arcade from './ArcadeShell.module.css'
import styles from './MelonStage.module.css'
import { useBoardTap, VIEW } from './useBoardTap'

type Point = [number, number]
type Effect = {
  player: number
  result: 'slice' | 'perfect' | 'air'
  points: number
  piece: Point[]
  cut: [Point, Point] | null
  position: Point | null
}
type Fruit = 'watermelon' | 'orange' | 'kiwi' | 'dragonfruit' | 'lime'
type Burst = { key: number; fruit: Fruit; effect: Effect }

// juice colour of each fruit (drops and the slash glow)
const JUICE: Record<Fruit, string> = {
  watermelon: '#ff3b4e',
  orange: '#ff9f1c',
  kiwi: '#8bd346',
  dragonfruit: '#ff3fa4',
  lime: '#b5e61d',
}
const DROPS = Array.from({ length: 12 }, (_, i) => ({
  angle: (i * 360) / 12 + (i % 3) * 9,
  reach: 16 + ((i * 7) % 5) * 5,
  size: 2 + (i % 3),
}))

const points = (polygon: Point[]) => polygon.map(([x, y]) => `${x},${-y}`).join(' ')

/** Melon samurai: a fruit covers the board, every dart is a sword cut through where it landed,
 *  across the line to the bull. The piece on the dart's side flies off. */
export default function MelonStage({
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
  const fruit = (game.fruit ?? 'orange') as Fruit
  const left = (game.fruit_left ?? []) as Point[]
  const darts = game.arcade_darts ?? []
  const effect = game.last_effect as Effect | null | undefined
  const [burst, setBurst] = useState<Burst | null>(null)
  const lastEvent = useRef(game.event_count)

  // the latest cut, keyed by event number so the animation restarts every dart
  useEffect(() => {
    if (game.event_count <= lastEvent.current) {
      lastEvent.current = game.event_count
      return
    }
    lastEvent.current = game.event_count
    if (!effect?.position) return
    setBurst({ key: game.event_count, fruit, effect })
    const timer = window.setTimeout(() => setBurst(null), 1400)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.event_count, effect])

  const fruitName = t(`arcade.fruits.${fruit}`)
  const multiplier = game.double_round ? 2 : 1
  const share = effect ? effect.points / multiplier / 1000 : 0
  const banner = game.awaiting_next
    ? t('play.pullDarts')
    : effect && darts.length > 0
      ? effect.result === 'perfect'
        ? t('arcade.melon.perfect')
        : effect.result === 'air'
          ? t('arcade.melon.air')
          : share >= 0.4
            ? t('arcade.melon.master')
            : share >= 0.25
              ? t('arcade.melon.clean')
              : share >= 0.1
                ? t('arcade.melon.nice')
                : t('arcade.melon.peel')
      : game.double_round
        ? t('arcade.melon.finale')
        : t('arcade.melon.instruction', { fruit: fruitName })

  const image = (name: string) => (
    <image href={`/arcade/melon/${name}.webp`} x={-R.doubleOuter} y={-R.doubleOuter} width={2 * R.doubleOuter} height={2 * R.doubleOuter} />
  )
  const cut = burst?.effect
  const key = burst?.key ?? 0
  const cutFruit = burst?.fruit ?? fruit
  const juice = JUICE[cutFruit]
  // the piece flies off away from the bull
  const away = cut?.position ? Math.atan2(cut.position[1], cut.position[0]) : 0
  const flight = {
    '--dx': `${Math.cos(away) * 90}px`,
    '--dy': `${-Math.sin(away) * 90}px`,
    '--spin': `${Math.cos(away) >= 0 ? 35 : -35}deg`,
  } as CSSProperties

  return (
    <ArcadeShell game={game} banner={banner} dartsThrown={darts.length} introLine={fruitName}>
      <svg {...board} aria-label={t('arcade.melon.board')}>
        <defs>
          <clipPath id="melonClip">
            <circle r={VIEW - 1} />
          </clipPath>
          <clipPath id="fruitLeft">
            <polygon points={points(left)} />
          </clipPath>
          {cut && cut.piece.length > 2 && (
            <clipPath id={`piece-${key}`}>
              <polygon points={points(cut.piece)} />
            </clipPath>
          )}
          <radialGradient id="melonVignette">
            <stop offset="70%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.55" />
          </radialGradient>
        </defs>
        <image
          href="/arcade/melon/dojo.webp"
          x={-VIEW}
          y={-VIEW}
          width={2 * VIEW}
          height={2 * VIEW}
          clipPath="url(#melonClip)"
          preserveAspectRatio="xMidYMid slice"
        />
        <circle r={VIEW} fill="url(#melonVignette)" />

        {/* what is left of the fruit; a new turn drops in a fresh one */}
        <g key={`${game.id}-${game.round}-${game.current_player}`} className={game.double_round ? `${styles.fruit} ${styles.finale}` : styles.fruit}>
          {left.length > 2 && (
            <>
              <g clipPath="url(#fruitLeft)">{image(fruit)}</g>
              <polygon points={points(left)} className={styles.outline} />
            </>
          )}
        </g>

        {/* the piece that was just cut off */}
        {cut && cut.piece.length > 2 && (
          <g key={`piece-${key}`} className={cut.result === 'perfect' ? styles.perfect : styles.flyOff} style={flight}>
            <g clipPath={`url(#piece-${key})`}>{image(cutFruit)}</g>
            <polygon points={points(cut.piece)} className={styles.outline} />
          </g>
        )}

        {/* the numbers and the bull as the target, no wires over the fruit */}
        <BoardLines wires={false} />
        <circle r={R.outerBull} className={styles.target} />
        <circle r={R.bull} className={styles.targetBull} />

        {cut?.cut && (
          <line
            key={`slash-${key}`}
            x1={cut.cut[0][0]}
            y1={-cut.cut[0][1]}
            x2={cut.cut[1][0]}
            y2={-cut.cut[1][1]}
            pathLength={1}
            className={styles.slash}
            style={{ '--juice': juice } as CSSProperties}
          />
        )}

        {darts.map((d, i) =>
          d.position ? (
            <g key={i} style={{ transform: `translate(${d.position[0]}px, ${-d.position[1]}px)` }}>
              <g className={arcade.dart}>
                <circle r={4.5} />
                <circle r={1.6} className={arcade.dartTip} />
              </g>
            </g>
          ) : null,
        )}

        {cut?.position && (
          <g key={`fx-${key}`} style={{ transform: `translate(${cut.position[0]}px, ${-cut.position[1]}px)` }}>
            {cut.result === 'air' ? (
              <g className={arcade.dust}>
                {[0, 60, 120, 180, 240, 300].map((a) => (
                  <circle key={a} r={3} cx={Math.cos((a * Math.PI) / 180) * 6} cy={Math.sin((a * Math.PI) / 180) * 6} />
                ))}
              </g>
            ) : (
              DROPS.map((drop, i) => {
                const a = (drop.angle * Math.PI) / 180
                const reach = drop.reach * (cut.result === 'perfect' ? 2.2 : 1)
                return (
                  <circle
                    key={i}
                    r={drop.size}
                    fill={juice}
                    className={styles.drop}
                    style={{ '--tx': `${Math.cos(a) * reach}px`, '--ty': `${Math.sin(a) * reach}px` } as CSSProperties}
                  />
                )
              })
            )}
            <text y={-10} className={cut.points > 0 ? arcade.popup : arcade.popupBad}>
              {cut.result === 'perfect' ? `${t('arcade.melon.perfectShort')} +${cut.points}` : cut.points > 0 ? `+${cut.points}` : t('arcade.melon.airShort')}
            </text>
          </g>
        )}
      </svg>
    </ArcadeShell>
  )
}
