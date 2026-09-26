import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameState } from './api'

/** Caller voice (Web Speech API), short sounds and celebration banners for the running game. */

export type AudioPrefs = { caller: boolean; sounds: boolean }
const STORAGE_KEY = 'dartscore.audio'
const DEFAULTS: AudioPrefs = { caller: true, sounds: true }

function load(): AudioPrefs {
  try {
    return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<AudioPrefs>) }
  } catch {
    return DEFAULTS
  }
}

let prefs = load()
const subscribers = new Set<() => void>()

export function setAudioPref(key: keyof AudioPrefs, value: boolean) {
  prefs = { ...prefs, [key]: value }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // private mode: the setting lasts until reload
  }
  subscribers.forEach((notify) => notify())
}

export function useAudioPrefs(): AudioPrefs {
  return useSyncExternalStore(
    (notify) => {
      subscribers.add(notify)
      return () => subscribers.delete(notify)
    },
    () => prefs,
  )
}

export const speechAvailable = typeof window !== 'undefined' && 'speechSynthesis' in window

function speak(text: string, language: string) {
  if (!speechAvailable || !prefs.caller) return
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = language.startsWith('de') ? 'de-DE' : 'en-GB'
  utterance.rate = 1.05
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(utterance)
}

let audio: AudioContext | null = null

// Browsers (Firefox in particular) keep audio muted until the page was touched once; the first
// interaction creates/resumes the audio context so later sounds - e.g. for detected darts - play.
function unlockAudio() {
  try {
    audio ??= new AudioContext()
    void audio.resume()
  } catch {
    // no audio output
  }
}
if (typeof window !== 'undefined') {
  for (const type of ['pointerdown', 'keydown', 'touchstart'] as const) {
    window.addEventListener(type, unlockAudio, { capture: true, passive: true })
  }
}

/** A short tone; ``kind`` picks the pitch. */
function beep(kind: 'dart' | 'bust' | 'win') {
  if (!prefs.sounds) return
  try {
    audio ??= new AudioContext()
    if (audio.state === 'suspended') void audio.resume()
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    const now = audio.currentTime
    const length = kind === 'win' ? 0.5 : 0.12
    osc.type = kind === 'bust' ? 'sawtooth' : 'sine'
    osc.frequency.setValueAtTime(kind === 'bust' ? 180 : kind === 'win' ? 660 : 880, now)
    if (kind === 'win') osc.frequency.linearRampToValueAtTime(990, now + length)
    gain.gain.setValueAtTime(0.15, now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + length)
    osc.connect(gain).connect(audio.destination)
    osc.start(now)
    osc.stop(now + length)
  } catch {
    // no audio output
  }
}

export type Celebration = { key: number; kind: '180' | 'checkout' | 'bust'; text: string }

/** Watches the game state and calls scores, plays sounds and returns a banner to show. */
export function useCaller(game: GameState | null): Celebration | null {
  const { t, i18n } = useTranslation()
  const previous = useRef<GameState | null>(null)
  const [celebration, setCelebration] = useState<Celebration | null>(null)

  useEffect(() => {
    const prev = previous.current
    previous.current = game
    // only react to one new event of the same game (not to loading, undo or corrections)
    if (!game || !prev || prev.id !== game.id || game.event_count !== prev.event_count + 1) return
    const lang = i18n.language
    const celebrate = (kind: Celebration['kind'], text: string) => setCelebration({ key: Date.now(), kind, text })
    const x01 = game.mode === 'x01'
    const newDart = (game.turn?.darts.length ?? 0) > (prev.turn?.player === game.turn?.player ? (prev.turn?.darts.length ?? 0) : 0)

    // leg or game won
    if ((game.leg_winner !== null && prev.leg_winner === null) || (game.finished && !prev.finished)) {
      const winner = game.players[game.winner ?? game.leg_winner ?? 0]
      beep('win')
      const text = game.finished ? t('caller.gameShotMatch', { name: winner.name }) : t('caller.gameShot')
      speak(text, lang)
      celebrate('checkout', game.finished ? t('caller.winner', { name: winner.name }) : t('caller.gameShot'))
      return
    }
    if (newDart) beep('dart')

    // a turn was completed: by the third dart / a bust (awaiting "next") or by "next"
    const closed = game.awaiting_next && !prev.awaiting_next ? game.turn : null
    const skipped = !closed && game.current_player !== prev.current_player && prev.turn && !prev.turn.closed ? prev.turn : null
    const turn = closed ?? skipped
    if (turn && x01) {
      const total = turn.values.reduce((sum, v) => sum + v, 0)
      if (turn.bust) {
        beep('bust')
        speak(t('caller.noScore'), lang)
        celebrate('bust', t('caller.bust'))
      } else if (total === 180) {
        speak(t('caller.oneEighty'), lang)
        celebrate('180', '180!')
      } else {
        speak(total === 0 ? t('caller.noScore') : String(total), lang)
      }
      return
    }

    // a new X01 turn begins with a possible checkout
    if (x01 && game.current_player !== prev.current_player && game.checkout && !game.awaiting_next) {
      const remaining = game.remaining?.[game.current_player]
      window.setTimeout(
        () => speak(t('caller.require', { name: game.players[game.current_player].name, score: remaining }), lang),
        1200,
      )
    }
  }, [game, t, i18n.language])

  // banners disappear on their own
  useEffect(() => {
    if (!celebration) return
    const timer = window.setTimeout(() => setCelebration(null), 2500)
    return () => window.clearTimeout(timer)
  }, [celebration])

  return celebration
}
