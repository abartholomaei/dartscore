import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from './api'

/** What the current player aims at in a training mode (null for X01/Cricket). Labels: a
 *  number ("20"), a field ("D16", "T20", "S5"), "BULL"/"25", or "D"/"T" for any double/triple. */
export function trainingTarget(game: GameState): string | null {
  switch (game.mode) {
    case 'around_the_clock':
      return game.current_targets?.[game.current_player] ?? null
    case 'shanghai':
      return game.round ? String(game.round) : null
    case 'bobs_27':
    case 'doubles_training':
    case 'halve_it':
    case 'segment_training':
      return game.target ?? null
    case 'killer': {
      const p = game.current_player
      return game.killer?.[p] ? null : game.numbers ? `D${game.numbers[p]}` : null
    }
    default:
      return null
  }
}

/** Readable form of a target label ("D" -> "Any double"). */
export function useTargetText() {
  const { t } = useTranslation()
  return useCallback(
    (label: string) => {
      if (label === 'D') return t('target.anyDouble')
      if (label === 'T') return t('target.anyTriple')
      if (label === 'BULL') return 'Bull'
      return label
    },
    [t],
  )
}

/** Stadium caller clips for a target, e.g. "D16" -> double, sixteen. */
export function targetClips(label: string): string[] | null {
  if (label === 'D') return ['any_double']
  if (label === 'T') return ['any_treble']
  if (label === 'BULL') return ['bullseye']
  const match = /^([SDT]?)(\d+)$/.exec(label)
  if (!match) return null
  const number = [`num_${match[2]}`]
  return match[1] === 'D' ? ['double', ...number] : match[1] === 'T' ? ['treble', ...number] : number
}

/** Spoken form for the browser voice. */
export function targetSpeech(label: string, t: (key: 'target.anyDouble' | 'target.anyTriple' | 'target.double' | 'target.triple') => string): string {
  if (label === 'D') return t('target.anyDouble')
  if (label === 'T') return t('target.anyTriple')
  if (label === 'BULL') return 'Bullseye'
  const match = /^([SDT]?)(\d+)$/.exec(label)
  if (!match) return label
  return match[1] === 'D' ? `${t('target.double')} ${match[2]}` : match[1] === 'T' ? `${t('target.triple')} ${match[2]}` : match[2]
}
