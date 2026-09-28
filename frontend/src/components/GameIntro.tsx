import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import type { GamePlayer, GameState } from '../api'
import Avatar from './Avatar'
import styles from './GameIntro.module.css'

const SEEN_KEY = 'dartscore.introSeen'
const VERSUS_DURATION = 3400
// line-up of more than two: every player gets a short moment, the whole show stays below ~8 s
const lineUpStep = (count: number) => Math.max(1000, Math.min(1500, 8000 / count))

function seenGames(): number[] {
  try {
    return JSON.parse(sessionStorage.getItem(SEEN_KEY) ?? '[]') as number[]
  } catch {
    return []
  }
}

function markSeen(id: number) {
  try {
    sessionStorage.setItem(SEEN_KEY, JSON.stringify([...seenGames().slice(-20), id]))
  } catch {
    // no storage: the intro may show again after a reload
  }
}

/** Whether the opening intro should run: a fresh game (nothing thrown yet) with at least two
 *  entries that this browser has not introduced yet. The bull-off is skipped, the game after it
 *  gets the intro. */
export function useGameIntro(game: GameState | null, enabled: boolean) {
  const [done, setDone] = useState<number[]>(seenGames)
  const show =
    enabled &&
    !!game &&
    !game.finished &&
    game.mode !== 'bull_off' &&
    game.players.length >= 2 &&
    game.event_count === 0 &&
    !done.includes(game.id)
  const id = game?.id
  // stable, so a game update from the server does not restart the intro's timers
  const finish = useCallback(() => {
    if (id === undefined) return
    markSeen(id)
    setDone((ids) => [...ids, id])
  }, [id])
  return { show, finish }
}


function Fighter({ player, side }: { player: GamePlayer; side?: 'left' | 'right' }) {
  const { t } = useTranslation()
  const members = player.members ?? []
  return (
    <div className={`${styles.fighter} ${side ? styles[side] : ''}`} style={{ '--player': player.color } as CSSProperties}>
      {members.length > 0 ? (
        <span className={styles.team}>
          {members.map((m) => (
            <span key={m.position} className={styles.avatar}>
              <Avatar name={m.name} color={m.color} avatar={m.avatar} size={members.length > 2 ? 96 : 128} />
            </span>
          ))}
        </span>
      ) : (
        <span className={styles.avatar}>
          <Avatar name={player.name} color={player.color} avatar={player.avatar} size={200} />
        </span>
      )}
      <span className={styles.name}>
        {player.bot_level ? '🤖 ' : ''}
        {player.name}
      </span>
      {members.length > 0 && <span className={styles.detail}>{members.map((m) => m.name).join(' · ')}</span>}
      {!!player.bot_level && <span className={styles.detail}>{t('newGame.botAverage', { average: player.bot_level })}</span>}
    </div>
  )
}

/** Opening of a game: two entries face each other like a boss fight (left, VS, right); with
 *  more, the players are introduced one after another in throwing order. Tap to skip. */
export default function GameIntro({ game, onDone }: { game: GameState; onDone: () => void }) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const players = game.players
  const versus = players.length === 2
  const step = lineUpStep(players.length)
  const title = game.mode === 'x01' && game.settings.start_score ? String(game.settings.start_score) : t(`modes.${game.mode}`)

  useEffect(() => {
    const timer = window.setTimeout(
      () => {
        if (versus || index >= players.length - 1) onDone()
        else setIndex(index + 1)
      },
      versus ? VERSUS_DURATION : step,
    )
    return () => window.clearTimeout(timer)
  }, [index, versus, step, players.length, onDone])

  if (versus) {
    return (
      <div className={`${styles.overlay} ${styles.versus}`} onClick={onDone} role="status" aria-live="assertive">
        <div className={styles.heading}>{title}</div>
        <div className={styles.arena}>
          <div className={`${styles.half} ${styles.halfLeft}`} style={{ '--player': players[0].color } as CSSProperties} />
          <div className={`${styles.half} ${styles.halfRight}`} style={{ '--player': players[1].color } as CSSProperties} />
          <Fighter player={players[0]} side="left" />
          <span className={styles.vs}>{t('play.versus')}</span>
          <Fighter player={players[1]} side="right" />
        </div>
        <div className={styles.flash} />
      </div>
    )
  }

  const player = players[index]
  return (
    <div
      className={`${styles.overlay} ${styles.lineUp}`}
      onClick={onDone}
      role="status"
      aria-live="assertive"
      style={{ '--step': `${step}ms` } as CSSProperties}
    >
      <div className={styles.heading}>{title}</div>
      <div key={index} className={styles.slot}>
        <div className={styles.band} style={{ '--player': player.color } as CSSProperties} />
        <span className={styles.order}>{t('play.introOrder', { position: index + 1, count: players.length })}</span>
        <Fighter player={player} />
      </div>
      <div className={styles.dots}>
        {players.map((p, i) => (
          <span
            key={p.position}
            className={`${styles.dot} ${i === index ? styles.dotActive : ''} ${i < index ? styles.dotDone : ''}`}
            style={{ '--player': p.color } as CSSProperties}
          />
        ))}
      </div>
    </div>
  )
}
