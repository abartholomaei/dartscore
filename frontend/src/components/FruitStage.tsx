import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { GameState } from '../api'
import { R, SEGMENT_DEG, SEGMENTS, scoreAt } from '../dart'
import Avatar from './Avatar'
import styles from './FruitStage.module.css'

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

const VIEW = 200 // mm shown around the bull (the board ends at 170)

// juice colour of each fruit (drops and the slash glow)
const JUICE: Record<Fruit, string> = {
  watermelon: '#ff3b4e',
  orange: '#ff9f1c',
  kiwi: '#8bd346',
  dragonfruit: '#ff3fa4',
  lime: '#b5e61d',
}
// lighter bits of flesh flying with the juice
const PULP: Record<Fruit, string> = {
  watermelon: '#ff8a95',
  orange: '#ffd08a',
  kiwi: '#c8f08a',
  dragonfruit: '#fff1f7',
  lime: '#e4ff9a',
}
const HAS_SEEDS: Record<Fruit, boolean> = { watermelon: true, orange: false, kiwi: true, dragonfruit: true, lime: false }

/** Deterministic 0..1 noise for the ambient petals. */
const noise = (n: number) => {
  const s = Math.sin(n * 12.9898) * 43758.5453
  return s - Math.floor(s)
}
// cherry blossom petals drifting down at the sides, where the board does not cover the scene
const PETALS = Array.from({ length: 14 }, (_, i) => ({
  left: i % 2 ? 2 + noise(i + 20) * 22 : 76 + noise(i + 21) * 22,
  t: 10 + noise(i + 22) * 9,
  d: -noise(i + 23) * 20,
  size: 8 + noise(i + 24) * 8,
}))

const points = (polygon: Point[]) => polygon.map(([x, y]) => `${x},${-y}`).join(' ')

type Particle = { x: number; y: number; kind: 'drop' | 'pulp' | 'seed'; size: number; style: CSSProperties }

/** A thrown particle: sideways at constant speed, a small hop and then falling faster and faster
 *  (CSS: --dx sideways, --hop up, --fall down, --spin, --dur, --delay; svg coordinates). */
const throwVars = (dx: number, hop: number, fall: number, spin: number, dur: number, delay = 0) =>
  ({
    '--dx': `${dx}px`,
    '--hop': `${hop}px`,
    '--fall': `${fall}px`,
    '--spin': `${spin}deg`,
    '--dur': `${dur}s`,
    '--delay': `${delay}s`,
  }) as CSSProperties

/** Juice, bits of flesh and seeds spraying from the cut (svg coordinates, y down). */
function spray(effect: Effect, fruit: Fruit, seed: number): Particle[] {
  const at = effect.position ?? [0, 0]
  const len = Math.hypot(at[0], at[1]) || 1
  // away from the bull, in svg coordinates
  const n: Point = [at[0] / len, -at[1] / len]
  const big = effect.result === 'perfect'
  const source = (i: number): Point => {
    if (!effect.cut) return [at[0], -at[1]]
    const u = 0.15 + noise(seed + i * 3) * 0.7
    const [[x1, y1], [x2, y2]] = effect.cut
    return [x1 + (x2 - x1) * u, -(y1 + (y2 - y1) * u)]
  }
  const direction = (i: number): Point => {
    if (big) {
      const a = noise(seed + i * 5) * Math.PI * 2
      return [Math.cos(a), Math.sin(a)]
    }
    // mostly to the side of the piece, some back over the rest of the fruit
    const side = noise(seed + i * 7) < 0.72 ? 1 : -1
    const a = (noise(seed + i * 11) - 0.5) * 1.3
    const [dx, dy] = [n[0] * side, n[1] * side]
    return [dx * Math.cos(a) - dy * Math.sin(a), dx * Math.sin(a) + dy * Math.cos(a)]
  }
  const make = (i: number, kind: Particle['kind'], size: number, speed: number, dur: number): Particle => {
    const [x, y] = source(i)
    const [dx, dy] = direction(i)
    const v = speed * (0.5 + noise(seed + i * 13)) * (big ? 1.6 : 1)
    const hop = Math.min(dy * v, 0) - 6 - noise(seed + i * 17) * 14
    const fall = Math.max(dy * v, 0) + 90 + noise(seed + i * 19) * 120
    const spin = (noise(seed + i * 23) - 0.5) * 720
    return { x, y, kind, size, style: throwVars(dx * v, hop, fall, spin, dur + noise(seed + i * 29) * 0.3, noise(seed + i * 31) * 0.08) }
  }
  const list: Particle[] = []
  for (let i = 0; i < (big ? 42 : 30); i++) list.push(make(i, 'drop', 2 + noise(seed + i) * 3, 90, 0.75))
  for (let i = 0; i < 10; i++) list.push(make(100 + i, 'pulp', 2.6 + noise(seed + i + 50) * 2.6, 65, 0.95))
  if (HAS_SEEDS[fruit]) for (let i = 0; i < 6; i++) list.push(make(200 + i, 'seed', 1.6, 70, 0.95))
  return list
}

/** Juice stains around every cut of the round, fixed per cut (svg coordinates). */
function stains(cuts: [number, number, number, number][]): { x: number; y: number; r: number }[] {
  return cuts.flatMap(([x1, y1, x2, y2], c) => {
    const len = Math.hypot(x2 - x1, y2 - y1) || 1
    const [px, py] = [-(y2 - y1) / len, (x2 - x1) / len]
    const seed = Math.round(x1 * 3 + y1 * 7 + x2 * 11) + c
    return Array.from({ length: 6 }, (_, i) => {
      const u = 0.1 + noise(seed + i) * 0.8
      const off = (noise(seed + i + 40) - 0.5) * 26
      return { x: x1 + (x2 - x1) * u + px * off, y: -(y1 + (y2 - y1) * u + py * off), r: 1.5 + noise(seed + i + 80) * 4 }
    })
  })
}

// idle glints twinkling on the fruit
const GLINTS = Array.from({ length: 4 }, (_, i) => {
  const a = noise(i + 60) * Math.PI * 2
  const r = 40 + noise(i + 61) * 90
  return { x: Math.cos(a) * r, y: Math.sin(a) * r, d: i * 1.3 }
})

/** Fruit samurai, full screen: a dojo with the fruit on the board in the middle. Every dart is
 *  a sword cut through where it landed, across the line to the bull; the piece on the dart's
 *  side flies off. Tapping the board throws a dart there, tapping a used blade corrects that
 *  dart. `children` go into the bottom toolbar. */
export default function FruitStage({
  game,
  onTap,
  onCorrect,
  disabled,
  children,
}: {
  game: GameState
  onTap?: (label: string, x: number, y: number) => void
  onCorrect?: (dart: number) => void
  disabled?: boolean
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const svg = useRef<SVGSVGElement>(null)
  const fruit = (game.fruit ?? 'orange') as Fruit
  const left = (game.fruit_left ?? []) as Point[]
  const darts = game.arcade_darts ?? []
  const effect = game.last_effect as Effect | null | undefined
  const [burst, setBurst] = useState<Burst | null>(null)
  const [intro, setIntro] = useState<{ key: string; round: number; name: string; fruit: Fruit } | null>(null)
  const [fullscreen, setFullscreen] = useState(() => !!document.fullscreenElement)
  const lastEvent = useRef(game.event_count)
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

  // the latest cut, keyed by event number so the animation restarts every dart
  useEffect(() => {
    const newer = game.event_count > lastEvent.current
    lastEvent.current = game.event_count
    if (!newer || !effect?.position || darts.length === 0) return
    setBurst({ key: game.event_count, fruit, effect })
    const timer = window.setTimeout(() => setBurst(null), 1900)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.event_count, effect])

  // "Round 3 · Kiwi - Alex" between turns
  const player = game.players[game.current_player]
  const introKey = `${game.id}-${game.round}-${game.current_player}`
  useEffect(() => {
    if (game.finished || game.awaiting_next || darts.length > 0) return
    setIntro({ key: introKey, round: game.round ?? 1, name: player.name, fruit })
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

  const inTurn = darts.length > 0 && !!effect && effect.player === game.current_player
  const multiplier = game.double_round ? 2 : 1
  const share = effect ? effect.points / multiplier / 1000 : 0
  const banner = game.awaiting_next
    ? t('play.pullDarts')
    : inTurn && effect
      ? effect.result === 'perfect'
        ? t('arcade.fruit.perfect')
        : effect.result === 'air'
          ? t('arcade.fruit.air')
          : share >= 0.4
            ? t('arcade.fruit.master')
            : share >= 0.25
              ? t('arcade.fruit.clean')
              : share >= 0.1
                ? t('arcade.fruit.nice')
                : t('arcade.fruit.peel')
      : game.double_round
        ? t('arcade.fruit.finale')
        : t('arcade.fruit.instruction', { fruit: t(`arcade.fruits.${fruit}`) })

  const image = (name: string) => (
    <image href={`/arcade/fruit/${name}.webp`} x={-R.doubleOuter} y={-R.doubleOuter} width={2 * R.doubleOuter} height={2 * R.doubleOuter} />
  )
  const cut = burst?.effect
  const key = burst?.key ?? 0
  const cutFruit = burst?.fruit ?? fruit
  const juice = JUICE[cutFruit]
  // the board hangs on the wall: the piece gets a little push away from the bull, then falls
  // down out of the picture, turning
  const away = cut?.position ? Math.atan2(cut.position[1], cut.position[0]) : 0
  const fallStyle = throwVars(
    Math.cos(away) * 45,
    Math.min(-Math.sin(away) * 30, 0) - 14,
    720,
    (Math.cos(away) >= 0 ? 1 : -1) * (70 + noise(key) * 90),
    1.5,
  )
  const particles = cut && cut.result !== 'air' ? spray(cut, cutFruit, key) : []
  // a perfect cut shakes the screen (two copies of the keyframes so it restarts)
  const shake = cut?.result === 'perfect' ? styles[key % 2 ? 'shakeA' : 'shakeB'] : ''
  const turnPoints = game.turn && game.turn.player === game.current_player ? game.turn.values.reduce((a, b) => a + b, 0) : 0
  const fruits = (game.fruits ?? []) as Fruit[]
  const marks = game.board_marks ?? { cuts: [], holes: [] }
  const juiceStains = stains(marks.cuts)

  return (
    <div className={styles.stage}>
      <div className={styles.backdrop} aria-hidden />
      {!reducedMotion && (
        <div className={styles.ambient} aria-hidden>
          {PETALS.map((p, i) => (
            <span
              key={i}
              className={styles.petal}
              style={{ left: `${p.left}%`, width: p.size, height: p.size * 0.7, animationDuration: `${p.t}s`, animationDelay: `${p.d}s` }}
            />
          ))}
        </div>
      )}

      <header className={styles.hud}>
        <div className={styles.roundText}>
          {t('play.roundOf', { round: game.round ?? 1, total: game.rounds ?? 0 })}
          {game.double_round && <strong className={styles.double}> ×2</strong>}
        </div>
        <div className={styles.fruits} aria-hidden>
          {fruits.map((f, i) => (
            <img
              key={i}
              src={`/arcade/fruit/${f}.webp`}
              alt=""
              className={i + 1 < (game.round ?? 1) ? styles.fruitDone : i + 1 === game.round ? styles.fruitNow : styles.fruitOpen}
            />
          ))}
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
        <aside className={styles.players}>
          {game.players.map((p) => (
            <div key={p.position} className={`${styles.card} ${p.position === game.current_player ? styles.cardActive : ''}`}>
              <Avatar name={p.name} color={p.color} avatar={p.avatar} size={44} />
              <span className={styles.cardName}>{p.name}</span>
              <span className={styles.cardScore}>{game.scores?.[p.position] ?? 0}</span>
            </div>
          ))}
        </aside>

        <div className={`${styles.center} ${shake}`}>
          <svg
            ref={svg}
            className={`${styles.board} ${onTap && !disabled ? styles.tappable : ''}`}
            viewBox={`${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`}
            onClick={tap}
            role="img"
            aria-label={t('arcade.fruit.board')}
          >
            <defs>
              <clipPath id="fruitClip">
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
              <clipPath id="boardWood">
                <circle r={R.doubleOuter + 6} />
              </clipPath>
              <radialGradient id="boardShadow">
                <stop offset="88%" stopColor="#000" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#000" stopOpacity="0" />
              </radialGradient>
              <linearGradient id="fruitSheen">
                <stop offset="0" stopColor="#fff" stopOpacity="0" />
                <stop offset="0.5" stopColor="#fff" stopOpacity="0.55" />
                <stop offset="1" stopColor="#fff" stopOpacity="0" />
              </linearGradient>
              <radialGradient id="fruitVignette">
                <stop offset="70%" stopColor="#000" stopOpacity="0" />
                <stop offset="100%" stopColor="#000" stopOpacity="0.55" />
              </radialGradient>
            </defs>
            <circle r={VIEW + 12} cy={8} fill="url(#boardShadow)" />
            <image
              href="/arcade/fruit/dojo.webp"
              x={-VIEW}
              y={-VIEW}
              width={2 * VIEW}
              height={2 * VIEW}
              clipPath="url(#fruitClip)"
              preserveAspectRatio="xMidYMid slice"
            />
            <circle r={VIEW} fill="url(#fruitVignette)" />

            {/* what this round left in the wood: a groove for every cut, a hole for every dart */}
            <g clipPath="url(#boardWood)">
              {marks.cuts.map(([x1, y1, x2, y2], i) => (
                <g key={`cut-${i}`} className={styles.groove}>
                  <line x1={x1} y1={-y1} x2={x2} y2={-y2} className={styles.grooveLight} transform="translate(0.8 0.8)" />
                  <line x1={x1} y1={-y1} x2={x2} y2={-y2} className={styles.grooveDark} />
                </g>
              ))}
              {juiceStains.map((st, i) => (
                <circle key={`stain-${i}`} cx={st.x} cy={st.y} r={st.r} fill={JUICE[fruit]} className={styles.stain} />
              ))}
            </g>
            {marks.holes.map(([x, y], i) => (
              <g key={`hole-${i}`} style={{ transform: `translate(${x}px, ${-y}px)` }}>
                <circle r={3.4} className={styles.holeRim} />
                <circle r={2} className={styles.hole} />
              </g>
            ))}

            {/* what is left of the fruit; a new turn drops in a fresh one */}
            <g key={introKey} className={game.double_round ? `${styles.fruit} ${styles.finale}` : styles.fruit}>
              {left.length > 2 && (
                <>
                  <g clipPath="url(#fruitLeft)">
                    {image(fruit)}
                    {!reducedMotion && (
                      <>
                        <g transform="rotate(25)">
                          <rect x={-35} y={-220} width={70} height={440} fill="url(#fruitSheen)" className={styles.sheen} />
                        </g>
                        {GLINTS.map((g, i) => (
                          <g key={i} transform={`translate(${g.x} ${g.y})`}>
                            <path
                              d="M0 -9 L2 -2 L9 0 L2 2 L0 9 L-2 2 L-9 0 L-2 -2Z"
                              className={styles.glint}
                              style={{ animationDelay: `${g.d}s` }}
                            />
                          </g>
                        ))}
                      </>
                    )}
                  </g>
                  <polygon points={points(left)} className={styles.outline} />
                </>
              )}
            </g>

            {/* the piece that was just cut off */}
            {cut && cut.piece.length > 2 && (
              <g key={`piece-${key}`} className={styles.throwX} style={fallStyle}>
                <g className={styles.throwY}>
                  <g className={styles.spin}>
                    <g clipPath={`url(#piece-${key})`}>{image(cutFruit)}</g>
                    <polygon points={points(cut.piece)} className={styles.outline} />
                  </g>
                </g>
              </g>
            )}

            {/* the numbers and the bull as the target, no wires over the fruit */}
            {SEGMENTS.map((n, i) => {
              const c = ((90 - i * SEGMENT_DEG) * Math.PI) / 180
              return (
                <text key={n} x={186 * Math.cos(c)} y={-186 * Math.sin(c)} className={styles.number}>
                  {n}
                </text>
              )
            })}
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
                <g key={`${introKey}-${i}`} style={{ transform: `translate(${d.position[0]}px, ${-d.position[1]}px)` }}>
                  <g className={styles.dart}>
                    <circle r={4.5} />
                    <circle r={1.6} className={styles.dartTip} />
                  </g>
                </g>
              ) : null,
            )}

            {particles.map((pt, i) => (
              <g key={`p-${key}-${i}`} transform={`translate(${pt.x} ${pt.y})`}>
                <g className={styles.throwX} style={pt.style}>
                  <g className={styles.throwY}>
                    {pt.kind === 'drop' ? (
                      <g className={styles.drop}>
                        <circle r={pt.size} fill={juice} className={styles.dropBody} />
                        <circle r={pt.size * 0.35} cx={-pt.size * 0.35} cy={-pt.size * 0.35} className={styles.dropShine} />
                      </g>
                    ) : (
                      <ellipse
                        rx={pt.kind === 'seed' ? 1.6 : pt.size}
                        ry={pt.kind === 'seed' ? 2.6 : pt.size * 0.55}
                        fill={pt.kind === 'seed' ? (cutFruit === 'dragonfruit' || cutFruit === 'kiwi' ? '#111' : '#1a0d08') : PULP[cutFruit]}
                        className={styles.bit}
                      />
                    )}
                  </g>
                </g>
              </g>
            ))}

            {cut?.position && (
              <g key={`fx-${key}`} style={{ transform: `translate(${cut.position[0]}px, ${-cut.position[1]}px)` }}>
                {cut.result === 'air' ? (
                  <g className={styles.dust}>
                    {[0, 60, 120, 180, 240, 300].map((a) => (
                      <circle key={a} r={3} cx={Math.cos((a * Math.PI) / 180) * 6} cy={Math.sin((a * Math.PI) / 180) * 6} />
                    ))}
                  </g>
                ) : (
                  <circle r={cut.result === 'perfect' ? 30 : 16} fill={juice} className={cut.result === 'perfect' ? styles.mistBig : styles.mist} />
                )}
                <text y={-12} className={cut.result === 'perfect' ? styles.great : cut.points > 0 ? styles.good : styles.bad}>
                  {cut.result === 'perfect' ? `${t('arcade.fruit.perfectShort')} +${cut.points}` : cut.points > 0 ? `+${cut.points}` : t('arcade.fruit.airShort')}
                </text>
              </g>
            )}
          </svg>
        </div>

        <aside className={styles.blades}>
          <span className={styles.bladesTitle}>{t('arcade.fruit.blades')}</span>
          {[0, 1, 2].map((i) => {
            const used = i < darts.length
            return (
              <button
                key={i}
                className={`${styles.blade} ${used ? styles.bladeUsed : ''}`}
                disabled={!used || !onCorrect}
                onClick={() => onCorrect?.(i)}
                aria-label={used ? t('play.correctDart', { n: i + 1 }) : undefined}
              >
                <svg viewBox="0 0 24 72" className={styles.katana} aria-hidden>
                  <path d="M12 2 Q16 14 14.5 46 L9.5 46 Q10 14 12 2z" className={styles.steel} />
                  <path d="M12 6 Q14 16 13 44" className={styles.edge} />
                  <ellipse cx={12} cy={48} rx={8} ry={2.6} className={styles.guard} />
                  <rect x={9.5} y={50} width={5} height={18} rx={2} className={styles.grip} />
                  <path d="M9.5 54 L14.5 57 M9.5 59 L14.5 62 M9.5 64 L14.5 67" className={styles.wrap} />
                </svg>
                <span className={styles.bladeLabel}>{darts[i]?.label ?? ''}</span>
              </button>
            )
          })}
          <span className={styles.turnPoints}>{turnPoints}</span>
        </aside>
      </div>

      <footer className={styles.footer}>
        <div className={styles.banner} key={banner}>
          {banner}
        </div>
        <div className={styles.toolbar}>{children}</div>
      </footer>

      {intro && (
        <div key={intro.key} className={styles.intro}>
          <img src={`/arcade/fruit/${intro.fruit}.webp`} alt="" className={styles.introFruit} />
          <span>
            {t('play.roundOf', { round: intro.round, total: game.rounds ?? 0 })} · {t(`arcade.fruits.${intro.fruit}`)}
          </span>
          <strong>{t('arcade.yourTurn', { name: intro.name })}</strong>
        </div>
      )}
    </div>
  )
}
