import { createContext, useContext, useEffect, useState } from 'react'
import type { GameState } from './api'

type Live = {
  /** the active (or just finished) game; null if none */
  game: GameState | null
  /** false until the first message and while reconnecting */
  connected: boolean
  /** apply a state returned by a REST call right away (the WebSocket echo follows) */
  setGame: (game: GameState | null) => void
}

const LiveGameContext = createContext<Live>({ game: null, connected: false, setGame: () => undefined })

const RECONNECT_MS = 2000

/** Keeps one WebSocket to /ws open for the whole app and shares the live game state. */
export function LiveGameProvider({ children }: { children: React.ReactNode }) {
  const [game, setGame] = useState<GameState | null>(null)
  const [connected, setConnected] = useState(false)

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

  return <LiveGameContext.Provider value={{ game, connected, setGame }}>{children}</LiveGameContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLiveGame(): Live {
  return useContext(LiveGameContext)
}
