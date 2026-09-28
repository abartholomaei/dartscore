import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from '../api'
import Avatar from './Avatar'
import styles from './PlayerIntro.module.css'

type Intro = { key: string; name: string; color: string; avatar?: string | null; bot: boolean; team?: string; remaining?: number }

const DURATION = 1800

/** With more than two people at the board, briefly presents whoever throws next (full screen,
 *  zooming in) so everyone knows whose turn it is. Does not block input. */
export default function PlayerIntro({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const previous = useRef<string | null>(null)
  const [intro, setIntro] = useState<Intro | null>(null)

  const people = game.players.reduce((n, p) => n + (p.members?.length || 1), 0)
  const entry = game.players[game.current_player]
  const thrower = game.thrower ?? null
  const ready = !game.awaiting_next && game.leg_winner === null && !game.finished
  const key = `${game.id}:${game.set}:${game.leg}:${game.current_player}:${thrower?.name ?? ''}`

  useEffect(() => {
    if (!ready) return
    const before = previous.current
    previous.current = key
    if (before === key || people <= 2) return
    // opening the page in the middle of a game: no intro for the turn already running
    if (before === null && game.event_count > 0) return
    setIntro({
      key,
      name: thrower?.name ?? entry.name,
      color: thrower?.color ?? entry.color,
      avatar: thrower ? thrower.avatar : entry.avatar,
      bot: entry.bot_level !== null,
      team: thrower ? entry.name : undefined,
      remaining: game.mode === 'x01' ? game.remaining?.[game.current_player] : undefined,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready])

  useEffect(() => {
    if (!intro) return
    const timer = window.setTimeout(() => setIntro(null), DURATION)
    return () => window.clearTimeout(timer)
  }, [intro])

  if (!intro) return null
  return (
    <div
      key={intro.key}
      className={styles.overlay}
      style={{ '--player': intro.color } as CSSProperties}
      role="status"
      aria-live="assertive"
    >
      <div className={styles.band} />
      <div className={styles.content}>
        <span className={styles.label}>{t('play.upNext')}</span>
        <span className={styles.avatar}>
          <Avatar name={intro.name} color={intro.color} avatar={intro.avatar} size={160} />
        </span>
        <span className={styles.name}>
          {intro.bot ? '🤖 ' : ''}
          {intro.name}
        </span>
        {(intro.team || intro.remaining !== undefined) && (
          <span className={styles.detail}>
            {intro.team}
            {intro.team && intro.remaining !== undefined && ' · '}
            {intro.remaining !== undefined && t('play.introRemaining', { score: intro.remaining })}
          </span>
        )}
      </div>
    </div>
  )
}
