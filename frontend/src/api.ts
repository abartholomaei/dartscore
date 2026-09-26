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
  board_calibrated: boolean
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

export type Point = [number, number]

export type CalibrationCatalog = {
  required: number
  segments: number[]
  points: { id: string; x_mm: number; y_mm: number }[]
}

export type Overlay = {
  rings: Point[][]
  wires: [Point, Point][]
  labels: [number, Point][]
}

export type CalibrationPreview = {
  rms_px: number
  errors_px: Record<string, number>
  overlay: Overlay
}

export type Calibration = {
  camera_id: string
  points: Record<string, Point>
  image_size: [number, number]
  undistorted: boolean
  rms_px: number
  created_at: string
  stale: boolean
  drift_px: number | null
  drift_warning: boolean
  overlay: Overlay
}

export type ScoreResult = {
  label: string
  segment: number
  multiplier: number
  points: number
  x_mm: number
  y_mm: number
}

/** Error with the backend's `detail` message, if any. */
export class ApiError extends Error {
  readonly status: number
  /** stable error code from the backend, translated in the UI */
  readonly code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function sendJson<T>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    let code: string | undefined
    try {
      const data = (await res.json()) as { detail?: string | { code?: string; message?: string } }
      if (typeof data.detail === 'string') message = data.detail
      else if (data.detail) {
        message = data.detail.message ?? message
        code = data.detail.code
      }
    } catch {
      // no JSON body
    }
    throw new ApiError(res.status, message, code)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

/** GET that maps 404 to null (e.g. a camera without calibration). */
export async function getOptional<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  const res = await fetch(path, { signal })
  if (res.status === 404) return null
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
  return (await res.json()) as T
}

export function snapshotUrl(cameraId: string, opts: { width?: number; undistort?: boolean } = {}) {
  const params = new URLSearchParams({ t: String(Date.now()) })
  if (opts.width) params.set('width', String(opts.width))
  if (opts.undistort) params.set('undistort', 'true')
  return `/api/cameras/${encodeURIComponent(cameraId)}/snapshot.jpg?${params.toString()}`
}
