import { useEffect, useState } from 'react'
import { getJson } from './api'

export type PollState<T> =
  | { kind: 'loading' }
  | { kind: 'ok'; data: T }
  | { kind: 'error'; message: string }

/** Lädt `path` sofort und danach alle `intervalMs` erneut. */
export function usePolling<T>(path: string, intervalMs: number): PollState<T> {
  const [state, setState] = useState<PollState<T>>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined

    const load = async () => {
      try {
        const data = await getJson<T>(path, controller.signal)
        setState({ kind: 'ok', data })
      } catch (err: unknown) {
        if (controller.signal.aborted) return
        setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
      }
      if (!controller.signal.aborted) timer = window.setTimeout(load, intervalMs)
    }
    void load()

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [path, intervalMs])

  return state
}
