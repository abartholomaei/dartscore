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

export async function sendJson<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
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

// --- players, games, stats ------------------------------------------------------------

export type Player = {
  id: number
  name: string
  color: string
  created_at: string
  archived: boolean
}

export type PlayerGameStats = {
  darts: number
  turns: number
  legs_played: number
  legs_won: number
  won: boolean
  points: number
  highest_finish: number
  highest_turn: number
  best_leg_darts: number | null
  checkouts: number
  checkout_attempts: number
  busts: number
  tons: Record<'60' | '100' | '140' | '180', number>
  marks: number
  score: number | null
  hits: number
  hit_rate: number | null
  average: number | null
  first9_average: number | null
  checkout_rate: number | null
  mpr: number | null
}

export type GamePlayer = {
  position: number
  player_id: number | null
  name: string
  color: string
  guest: boolean
  stats: PlayerGameStats
}

export type TurnSummary = {
  player: number
  darts: string[]
  total: number
  bust: boolean
  checkout: boolean
}

export type GameMode =
  | 'x01'
  | 'cricket'
  | 'around_the_clock'
  | 'shanghai'
  | 'bobs_27'
  | 'checkout_training'
  | 'doubles_training'
export const TRAINING_MODES: GameMode[] = [
  'around_the_clock',
  'shanghai',
  'bobs_27',
  'checkout_training',
  'doubles_training',
]
export type InOutRule = 'single' | 'double' | 'master'
export type CricketVariant = 'standard' | 'cut_throat' | 'no_score'

export type GameState = {
  id: number
  event_count: number
  turn_sources: ('manual' | 'auto' | 'corrected' | 'bounce')[]
  turn_confidence: (number | null)[]
  mode: GameMode
  settings: Record<string, string | number>
  created_at: string
  players: GamePlayer[]
  history: TurnSummary[]
  player_count: number
  current_player: number
  leg: number
  set: number
  legs_won: number[]
  sets_won: number[]
  turn: {
    player: number
    darts: string[]
    values: number[]
    bust: boolean
    checkout: boolean
    closed: boolean
  } | null
  awaiting_next: boolean
  leg_winner: number | null
  finished: boolean
  winner: number | null
  // x01
  remaining?: number[]
  opened?: boolean[]
  checkout?: string[] | null
  // cricket (targets also used by training modes)
  targets?: number[]
  marks?: number[][]
  points?: number[]
  // training modes
  position?: number[]
  current_targets?: (string | null)[]
  scores?: number[]
  round?: number
  rounds?: number
  target?: string
  out?: boolean[]
  target_index?: number[]
  successes?: number[]
  results?: boolean[][]
  darts_on_target?: number[]
  hits?: number[]
  hits_by_target?: Record<string, number>[]
}

export type HistoryEntry = {
  id: number
  mode: GameMode
  settings: Record<string, string | number>
  status: 'finished' | 'aborted'
  created_at: string
  finished_at: string | null
  winner: number | null
  players: (Omit<GamePlayer, 'stats'> & { stats: PlayerGameStats | null })[]
}

export type AggregateStats = {
  games: number
  wins: number
  win_rate: number | null
  darts: number
  legs_played: number
  legs_won: number
  average: number | null
  first9_average: number | null
  checkout_rate: number | null
  checkouts: number
  checkout_attempts: number
  highest_finish: number
  highest_turn: number
  best_leg_darts: number | null
  darts_per_leg: number | null
  tons: Record<'60' | '100' | '140' | '180', number>
  mpr: number | null
  marks: number
  best_score: number | null
  average_score: number | null
  hit_rate: number | null
  trend: {
    game_id: number
    date: string
    average: number | null
    mpr: number | null
    score: number | null
    won: boolean
  }[]
}

export type PlayerStats = {
  player: { id: number; name: string; color: string }
  modes: Partial<Record<GameMode, AggregateStats>>
}

export type HeadToHead = {
  games: number
  wins: Record<string, number>
  stats: Record<string, AggregateStats>
}

export type DetectionHit = {
  camera_id: string
  tip_px: [number, number]
  board_mm: [number, number]
  area_px: number
  used: boolean
}

export type DetectedDart = {
  x_mm: number
  y_mm: number
  label: string
  segment: number
  multiplier: number
  confidence: number
  hits: DetectionHit[]
  accepted: boolean
  time: string
}

export type DetectionStatus = {
  enabled: boolean
  available: boolean
  cameras: string[]
  state: 'idle' | 'motion' | 'blocked' | 'unavailable'
  darts_in_turn: number
  last_dart: DetectedDart | null
}
