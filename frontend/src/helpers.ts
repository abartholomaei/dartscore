import type { TFunction } from 'i18next'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, type CricketVariant, type GameMode } from './api'

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
