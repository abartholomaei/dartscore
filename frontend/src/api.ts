export type Health = {
  status: string
  version: string
  cameras_configured: number
}

export type CameraInfo = {
  width: number
  height: number
  fps: number
  fourcc: string
  backend: string
}

export type CameraState = 'starting' | 'running' | 'reconnecting' | 'stopped'

export type CameraStatus = {
  id: string
  source: 'device' | 'synthetic'
  device: string
  position_deg: number
  state: CameraState
  fps: number
  frames: number
  dropped: number
  info: CameraInfo | null
  last_error: string | null
  lens_calibrated: boolean
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

export function streamUrl(cameraId: string, opts: { width?: number; undistort?: boolean } = {}) {
  const params = new URLSearchParams()
  if (opts.width) params.set('width', String(opts.width))
  if (opts.undistort) params.set('undistort', 'true')
  const query = params.toString()
  return `/api/cameras/${encodeURIComponent(cameraId)}/stream.mjpg${query ? `?${query}` : ''}`
}
