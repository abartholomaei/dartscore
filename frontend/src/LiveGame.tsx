import { createContext, useContext, useEffect, useState } from 'react'
import type { DetectedDart, DetectionStatus, GameState } from './api'

type Live = {
  /** the active (or just finished) game; null if none */
  game: GameState | null
  /** false until the first message and while reconnecting */
  connected: boolean
  /** apply a state returned by a REST call right away (the WebSocket echo follows) */
  setGame: (game: GameState | null) => void
  detection: DetectionStatus | null
  setDetection: (status: DetectionStatus) => void
  /** the most recently detected dart (also outside of games, e.g. for testing) */
  lastDart: DetectedDart | null
}

const LiveGameContext = createContext<Live>({
  game: null,
  connected: false,
  setGame: () => undefined,
  detection: null,
  setDetection: () => undefined,
  lastDart: null,
})

const RECONNECT_MS = 2000

/** Keeps one WebSocket to /ws open for the whole app and shares the live game state. */
export function LiveGameProvider({ children }: { children: React.ReactNode }) {
  const [game, setGame] = useState<GameState | null>(null)
  const [connected, setConnected] = useState(false)
  const [detection, setDetection] = useState<DetectionStatus | null>(null)
  const [lastDart, setLastDart] = useState<DetectedDart | null>(null)

  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: number | undefined
    let closed = false

    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${protocol}://${window.location.host}/ws`)
      socket.onmessage = (event: MessageEvent<string>) => {
        const message = JSON.parse(event.data) as { type: string; data: unknown }
        if (message.type === 'game') {
          setGame(message.data as GameState | null)
          setConnected(true)
        } else if (message.type === 'detection') {
          setDetection(message.data as DetectionStatus)
        } else if (message.type === 'dart') {
          setLastDart(message.data as DetectedDart)
        }
      }
      socket.onclose = () => {
        setConnected(false)
        if (!closed) timer = window.setTimeout(connect, RECONNECT_MS)
      }
    }
    connect()

    return () => {
      closed = true
      window.clearTimeout(timer)
      socket?.close()
    }
  }, [])

  return (
    <LiveGameContext.Provider value={{ game, connected, setGame, detection, setDetection, lastDart }}>
      {children}
    </LiveGameContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLiveGame(): Live {
  return useContext(LiveGameContext)
}
