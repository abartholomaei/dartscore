import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { GameState } from '../api'
import { R, SEGMENT_DEG, SEGMENTS, scoreAt } from '../dart'
import Avatar from './Avatar'
import MonsterPuppets, { type PuppetMonster, type PuppetShot } from './MonsterPuppets'
import styles from './ArcadeStage.module.css'

export type Monster = NonNullable<GameState['monsters']>[number]
type Effect = NonNullable<GameState['last_effect']>
type Popup = { key: number; x: number; y: number; text: string; tone: 'good' | 'great' | 'bad' }

const VIEW = 200 // mm shown around the bull (the board ends at 170)
const HEADSHOT: Record<string, number> = { easy: 0.45, medium: 0.35, hard: 0.3 } // as in the backend

/** Deterministic 0..1 noise, so a bullet hole keeps its cracks across renders. */
const noise = (n: number) => {
  const s = Math.sin(n * 12.9898) * 43758.5453
  return s - Math.floor(s)
}

// ambient life, fixed once: fireflies over the board, leaves drifting through the scene
const FIREFLIES = Array.from({ length: 18 }, (_, i) => {
  const a = noise(i + 1) * Math.PI * 2
  const r = 120 + noise(i + 7) * 80
  return { x: Math.cos(a) * r, y: Math.sin(a) * r, dx: (noise(i + 3) - 0.5) * 40, dy: (noise(i + 5) - 0.5) * 40, t: 5 + noise(i + 9) * 6, d: -noise(i + 11) * 10 }
})
const LEAVES = Array.from({ length: 12 }, (_, i) => ({
  // mostly at the sides, where the board does not cover the scene
  left: i % 2 ? 2 + noise(i + 20) * 22 : 76 + noise(i + 21) * 22,
  t: 11 + noise(i + 22) * 9,
  d: -noise(i + 23) * 20,
  size: 10 + noise(i + 24) * 10,
  hue: [28, 18, 45, 90][i % 4],
}))

/** Monster hunt, full screen: a night-time graveyard with the board in the middle. One monster
 *  at a time stands on the real board position, darts leave bullet holes where they landed,
 *  the three darts of a turn are the ammo. Tapping the board throws a dart there, tapping a
 *  spent cartridge corrects that dart. `children` go into the bottom toolbar. */
export default function ArcadeStage({
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
  const monsters = game.monsters ?? []
  const darts = game.arcade_darts ?? []
  const effect = game.last_effect
  const [popups, setPopups] = useState<Popup[]>([])
  // the latest dart, keyed by event number so its animations restart every dart
  const [shot, setShot] = useState<{ key: number; effect: Effect } | null>(null)
  const [intro, setIntro] = useState<{ key: string; round: number; name: string } | null>(null)
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

  // every new dart: shake, muzzle flash, pop-up
  useEffect(() => {
    const newer = game.event_count > lastEvent.current
    lastEvent.current = game.event_count
    if (!newer || !effect?.position || darts.length === 0) return
    setShot({ key: game.event_count, effect })
    const [x, y] = effect.position
    const target = monsters.find((m) => m.id === effect.target)
    const popup: Popup = effect.killed
      ? { key: game.event_count, x, y, text: effect.headshot ? `${t('arcade.headshot')} +${effect.points}` : `+${effect.points}`, tone: effect.headshot ? 'great' : 'good' }
      : effect.hit
        ? { key: game.event_count, x, y, text: t('arcade.lifeLost'), tone: 'good' }
        : { key: game.event_count, x: target?.x ?? x, y: target?.y ?? y, text: t('arcade.grow'), tone: 'bad' }
    setPopups((list) => [...list.slice(-4), popup])
    const timer = window.setTimeout(() => setPopups((list) => list.filter((p) => p.key !== popup.key)), 1500)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const inTurn = darts.length > 0 && !!effect && effect.player === game.current_player
  const current = monsters.find((m) => m.status === 'active')
  const lines = t('arcade.lines', { returnObjects: true }) as unknown as string[]
  const banner = game.awaiting_next
    ? t('play.pullDarts')
    : inTurn && effect
      ? effect.killed
        ? effect.headshot
          ? t('arcade.headshotPoints', { points: effect.points })
          : t('arcade.hit', { points: effect.points })
        : effect.hit
          ? t('arcade.graze', { count: current?.hp ?? 0 })
          : t('arcade.missed')
      : game.double_round
        ? t('arcade.doubleRound')
        : lines[((game.round ?? 1) + game.current_player) % lines.length]

  // on the board: the monster to shoot, and the one that just went down (it plays its fall)
  const shown = monsters.filter((m) => m.status === 'active' || (inTurn && effect?.killed && effect.target === m.id))
  const headshot = HEADSHOT[String(game.settings.difficulty)] ?? HEADSHOT.medium
  const puppets: PuppetMonster[] = shown.map((m) => ({ key: `${introKey}-${m.id}`, kind: m.kind, x: m.x, y: m.y, radius: m.radius, dying: m.status === 'dead' }))
  const puppetShot: PuppetShot | null =
    shot && inTurn
      ? {
          key: shot.key,
          target: shot.effect.target === null ? null : `${introKey}-${shot.effect.target}`,
          kind: shot.effect.killed ? (shot.effect.headshot ? 'headshot' : 'kill') : shot.effect.hit ? 'hit' : 'miss',
          fromX: shot.effect.position?.[0] ?? 0,
        }
      : null
  // two copies of each keyframe set, alternated, so the animation restarts on every dart
  const shake = shot && inTurn ? styles[`shake${shot.effect.headshot ? 'Big' : ''}${shot.key % 2 ? 'A' : 'B'}`] : ''
  const turnPoints = game.turn && game.turn.player === game.current_player ? game.turn.values.reduce((a, b) => a + b, 0) : 0

  return (
    <div className={styles.stage}>
      <div className={styles.backdrop} aria-hidden />
      {!reducedMotion && (
        <div className={styles.ambient} aria-hidden>
          <div className={styles.fog} />
          <div className={`${styles.fog} ${styles.fogLate}`} />
          {LEAVES.map((l, i) => (
            <span
              key={i}
              className={styles.leaf}
              style={{ left: `${l.left}%`, width: l.size, height: l.size * 0.6, animationDuration: `${l.t}s`, animationDelay: `${l.d}s`, '--hue': l.hue } as CSSProperties}
            />
          ))}
        </div>
      )}

      <header className={styles.hud}>
        <div className={styles.roundText}>
          {t('play.roundOf', { round: game.round ?? 1, total: game.rounds ?? 0 })}
          {game.double_round && <strong className={styles.double}> ×2</strong>}
        </div>
        <div className={styles.graves} aria-hidden>
          {Array.from({ length: game.rounds ?? 0 }, (_, i) => (
            <svg
              key={i}
              viewBox="0 0 20 24"
              className={i + 1 < (game.round ?? 1) ? styles.graveDone : i + 1 === game.round ? styles.graveNow : styles.grave}
            >
              <path d="M3 23V9a7 7 0 0 1 14 0v14z" />
              <path d="M10 7v8M7 10h6" className={styles.graveCross} />
            </svg>
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
              <span className={styles.cardKills}>★ {game.kills?.[p.position] ?? 0}</span>
            </div>
          ))}
        </aside>

        <div className={`${styles.center} ${shake}`}>
          <div className={styles.board}>
          <svg className={styles.layer} viewBox={`${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`} aria-hidden>
            <defs>
              <radialGradient id="arcadeFade">
                <stop offset="78%" stopColor="#fff" />
                <stop offset="100%" stopColor="#000" />
              </radialGradient>
              <mask id="arcadeMask">
                <circle r={VIEW} fill="url(#arcadeFade)" />
              </mask>
              <radialGradient id="arcadeGlow">
                <stop offset="0%" stopColor="#d9fff5" />
                <stop offset="35%" stopColor="#5eead4" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#5eead4" stopOpacity="0" />
              </radialGradient>
              <radialGradient id="arcadeShadow">
                <stop offset="0%" stopColor="#000" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#000" stopOpacity="0" />
              </radialGradient>
            </defs>

            <image
              href="/arcade/monster-night.webp"
              x={-VIEW}
              y={-VIEW}
              width={2 * VIEW}
              height={2 * VIEW}
              mask="url(#arcadeMask)"
              preserveAspectRatio="xMidYMid slice"
            />

            {/* the glowing board, see-through over the graveyard */}
            <circle r={R.doubleOuter} className={styles.boardFace} />
            <circle r={R.doubleOuter + 3} className={styles.halo} />
            <circle r={R.doubleOuter} className={styles.rim} />
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
                  <text x={185 * Math.cos(c)} y={-185 * Math.sin(c)} className={styles.number}>
                    {n}
                  </text>
                </g>
              )
            })}

            {!reducedMotion &&
              FIREFLIES.map((f, i) => (
                <circle
                  key={i}
                  cx={f.x}
                  cy={f.y}
                  r={2.6}
                  fill="url(#arcadeGlow)"
                  className={styles.firefly}
                  style={{ '--dx': `${f.dx}px`, '--dy': `${f.dy}px`, animationDuration: `${f.t}s`, animationDelay: `${f.d}s` } as CSSProperties}
                />
              ))}

            {shown.map((m) =>
              m.status === 'dead' ? null : (
                <g key={`${introKey}-${m.id}`} className={styles.monster} style={{ transform: `translate(${m.x}px, ${-m.y}px)` }}>
                  <g className={styles.spawn}>
                    <ellipse cy={m.radius * 1.05} rx={m.radius * 0.95} ry={m.radius * 0.32} fill="url(#arcadeShadow)" />
                    <g className={styles.reticle}>
                      <circle r={m.radius} className={styles.reticleRing} />
                      <circle r={m.radius * headshot} className={styles.reticleCore} />
                      {[0, 90, 180, 270].map((a) => (
                        <line
                          key={a}
                          x1={Math.cos((a * Math.PI) / 180) * (m.radius - 4)}
                          y1={Math.sin((a * Math.PI) / 180) * (m.radius - 4)}
                          x2={Math.cos((a * Math.PI) / 180) * (m.radius + 4)}
                          y2={Math.sin((a * Math.PI) / 180) * (m.radius + 4)}
                          className={styles.reticleTick}
                        />
                      ))}
                    </g>
                  </g>
                </g>
              ),
            )}
          </svg>

          <MonsterPuppets monsters={puppets} shot={puppetShot} view={VIEW} />

          <svg
            ref={svg}
            className={`${styles.layer} ${onTap && !disabled ? styles.tappable : ''}`}
            viewBox={`${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`}
            onClick={tap}
            role="img"
            aria-label={t('arcade.board')}
          >
            {shown.map((m) =>
              m.status === 'dead' ? null : (
                <g key={`${introKey}-${m.id}`} className={styles.monster} style={{ transform: `translate(${m.x}px, ${-m.y}px)` }}>
                  <g className={styles.spawn}>
                    {m.max_hp > 1 && (
                      <g aria-label={t('arcade.lives', { count: m.hp })}>
                        {Array.from({ length: m.max_hp }, (_, k) => (
                          <rect
                            key={k}
                            x={(k - m.max_hp / 2) * 9 + 0.5}
                            y={-m.radius * 1.9 - 6}
                            width={8}
                            height={4}
                            rx={2}
                            className={k < m.hp ? styles.life : styles.lifeLost}
                          />
                        ))}
                      </g>
                    )}
                    <g transform={`translate(0 ${m.radius * 1.55 + 6})`}>
                      <rect x={-13} y={-6.5} width={26} height={13} rx={6.5} className={styles.valueTag} />
                      <text className={styles.value}>{m.value}</text>
                    </g>
                  </g>
                </g>
              ),
            )}

            <defs>
              <radialGradient id="arcadeFlashTop">
                <stop offset="0%" stopColor="#fff" />
                <stop offset="40%" stopColor="#fde68a" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
              </radialGradient>
            </defs>
            {/* bullet holes of this turn: on top of everything, they stay until the darts are pulled */}
            {darts.map((d, i) => {
              if (!d.position) return null
              const [x, y] = d.position
              const seed = Math.round(x * 7 + y * 13) + i * 101
              return (
                <g key={`${introKey}-${i}`} style={{ transform: `translate(${x}px, ${-y}px)` }}>
                  <g className={styles.hole}>
                    <circle r={6.5} className={styles.scorch} />
                    {Array.from({ length: 7 }, (_, k) => {
                      const a = ((k + noise(seed + k) * 0.8) / 7) * Math.PI * 2
                      const len = 5 + noise(seed + k + 50) * 5
                      return <line key={k} x1={Math.cos(a) * 2.4} y1={Math.sin(a) * 2.4} x2={Math.cos(a) * len} y2={Math.sin(a) * len} className={styles.crack} />
                    })}
                    <circle r={2.8} className={styles.holeCore} />
                    <circle r={1.1} cx={-0.7} cy={-0.7} className={styles.holeDeep} />
                  </g>
                  <circle r={20} fill="url(#arcadeFlashTop)" className={styles.flash} />
                  <g className={styles.sparks}>
                    {Array.from({ length: 8 }, (_, k) => {
                      const a = ((k + noise(seed + k + 9)) / 8) * Math.PI * 2
                      return <line key={k} x1={Math.cos(a) * 4} y1={Math.sin(a) * 4} x2={Math.cos(a) * 9} y2={Math.sin(a) * 9} />
                    })}
                  </g>
                  <g className={styles.smoke}>
                    <circle r={4} cx={-2} />
                    <circle r={3.2} cx={2.5} cy={-2} />
                    <circle r={2.6} cy={-4} />
                  </g>
                </g>
              )
            })}

            {inTurn && effect?.killed && (
              <image
                key={`poof-${shot?.key}`}
                href="/arcade/poof.webp"
                x={(monsters.find((m) => m.id === effect.target)?.x ?? 0) - 30}
                y={-(monsters.find((m) => m.id === effect.target)?.y ?? 0) - 30}
                width={60}
                height={60}
                className={styles.poof}
              />
            )}
            {popups.map((p) => (
              <text key={p.key} x={p.x} y={-p.y - 12} className={styles[p.tone]}>
                {p.text}
              </text>
            ))}
          </svg>
          </div>
        </div>

        <aside className={styles.ammo}>
          <span className={styles.ammoTitle}>{t('arcade.ammo')}</span>
          {[0, 1, 2].map((i) => {
            const spent = i < darts.length
            const fresh = spent && i === darts.length - 1 && shot?.key === game.event_count
            return (
              <button
                key={i}
                className={`${styles.shell} ${spent ? styles.shellSpent : ''}`}
                disabled={!spent || !onCorrect}
                onClick={() => onCorrect?.(i)}
                aria-label={spent ? t('play.correctDart', { n: i + 1 }) : undefined}
              >
                <svg viewBox="0 0 24 64" className={styles.cartridge} aria-hidden>
                  <path d="M6 22 Q12 2 18 22z" className={styles.tip} />
                  <rect x={5} y={22} width={14} height={36} rx={2} className={styles.casing} />
                  <rect x={4} y={56} width={16} height={6} rx={1.5} className={styles.base} />
                  <rect x={8} y={25} width={3} height={28} rx={1.5} className={styles.shine} />
                </svg>
                {fresh && (
                  <svg key={shot?.key} viewBox="0 0 24 64" className={`${styles.cartridge} ${styles.eject}`} aria-hidden>
                    <rect x={5} y={22} width={14} height={36} rx={2} className={styles.casing} />
                    <rect x={4} y={56} width={16} height={6} rx={1.5} className={styles.base} />
                  </svg>
                )}
                <span className={styles.shellLabel}>{darts[i]?.label ?? ''}</span>
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
          <span>{t('play.roundOf', { round: intro.round, total: game.rounds ?? 0 })}</span>
          <strong>{t('arcade.yourTurn', { name: intro.name })}</strong>
        </div>
      )}
    </div>
  )
}
