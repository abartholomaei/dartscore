// Source of truth for UI strings. Every other locale must provide the same keys (enforced by type).
const en = {
  nav: {
    home: 'Home',
    cameras: 'Cameras',
  },
  language: {
    label: 'Language',
  },
  home: {
    backend: 'Backend',
    connecting: 'Connecting …',
    unreachable: 'Unreachable ({{message}})',
    status: 'Status',
    version: 'Version',
    cameras: 'Cameras',
  },
  cameras: {
    title: 'Cameras',
    undistort: 'Show undistorted',
    noLensCalibration: 'No lens calibration yet',
    loading: 'Loading …',
    backendUnreachable: 'Backend unreachable ({{message}})',
    noneConfigured: 'No cameras configured. See config.toml, section [[cameras]].',
    liveImage: 'Live image {{id}}',
    frameRate: 'Frame rate',
    fps: '{{value, number(minimumFractionDigits: 1; maximumFractionDigits: 1)}} fps',
    format: 'Format',
    position: 'Position',
    dropped: 'Dropped',
    droppedFrames_one: '{{count}} frame',
    droppedFrames_other: '{{count}} frames',
    lens: 'Lens',
    lensCalibrated: 'calibrated',
    lensNotCalibrated: 'not calibrated',
    source: 'Source',
    simulation: 'Simulation',
  },
  cameraState: {
    starting: 'starting',
    running: 'running',
    reconnecting: 'reconnecting',
    stopped: 'stopped',
  },
}

export default en

type DeepStringRecord<T> = { [K in keyof T]: T[K] extends string ? string : DeepStringRecord<T[K]> }
export type Translations = DeepStringRecord<typeof en>
