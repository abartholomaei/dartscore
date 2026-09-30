import type { TFunction } from 'i18next'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, type CricketVariant, type GameMode } from './api'

/** sessionStorage key: the game to start after a bull-off */
export const PENDING_KEY = 'dartscore.afterBullOff'

export type PendingGame = { mode: GameMode; settings: object; players: object[] }

export const PLAYER_COLORS = [
  '#e53935', '#1e88e5', '#43a047', '#fb8c00', '#8e24aa', '#00acc1', '#fdd835', '#6d4c41', '#546e7a', '#d81b60',
]  // prettier-ignore

/** Translates backend errors by their stable code, falls back to the message. */
export function useErrorText() {
  const { t } = useTranslation()
  return useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.code) return t(`errors.${err.code}`, { defaultValue: err.message })
      return err instanceof Error ? err.message : String(err)
    },
    [t],
  )
}

export function gameTitle(t: TFunction, mode: GameMode, settings: Record<string, string | number>) {
  if (mode === 'x01') return String(settings.start_score)
  if (mode === 'cricket') return `Cricket · ${t(`newGame.variants.${settings.variant as CricketVariant}`)}`
  return t(`modes.${mode}`)
}

/** Colour of a player's side: in a duel green against amber, like the two sides of a TV
 *  broadcast; with more players everyone keeps their own profile colour. */
export function sideColor(players: readonly { color: string }[], position: number): string {
  if (players.length === 2) return position === 0 ? 'var(--accent)' : 'var(--opponent)'
  return players[position]?.color ?? 'var(--text-muted)'
}

/** Readable text colour on a side colour (dark on light colours, white on dark ones). */
export function onSideColor(color: string): string {
  if (color === 'var(--accent)') return 'var(--on-accent)'
  if (color === 'var(--opponent)') return 'var(--on-opponent)'
  const hex = /^#([0-9a-f]{6})$/i.exec(color)?.[1]
  if (!hex) return '#fff'
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return luminance > 0.45 ? '#0b0b0c' : '#fff'
}
