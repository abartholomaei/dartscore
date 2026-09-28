import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from '../api'
import { R, SEGMENT_DEG, SEGMENTS } from '../dart'
import Avatar from './Avatar'
import styles from './ArcadeShell.module.css'

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
