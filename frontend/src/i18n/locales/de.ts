import type { Translations } from './en'

const de: Translations = {
  nav: {
    home: 'Start',
    cameras: 'Kameras',
  },
  language: {
    label: 'Sprache',
  },
  home: {
    backend: 'Backend',
    connecting: 'Verbinde …',
    unreachable: 'Nicht erreichbar ({{message}})',
    status: 'Status',
    version: 'Version',
    cameras: 'Kameras',
  },
  cameras: {
    title: 'Kameras',
    undistort: 'Entzerrt anzeigen',
    noLensCalibration: 'Noch keine Linsenkalibrierung',
    loading: 'Lade …',
    backendUnreachable: 'Backend nicht erreichbar ({{message}})',
    noneConfigured: 'Keine Kameras konfiguriert. Siehe config.toml, Abschnitt [[cameras]].',
    liveImage: 'Livebild {{id}}',
    frameRate: 'Bildrate',
    fps: '{{value, number(minimumFractionDigits: 1; maximumFractionDigits: 1)}} fps',
    format: 'Format',
    position: 'Position',
    dropped: 'Verloren',
    droppedFrames_one: '{{count}} Bild',
    droppedFrames_other: '{{count}} Bilder',
    lens: 'Linse',
    lensCalibrated: 'kalibriert',
    lensNotCalibrated: 'nicht kalibriert',
    source: 'Quelle',
    simulation: 'Simulation',
  },
  cameraState: {
    starting: 'startet',
    running: 'läuft',
    reconnecting: 'verbindet neu',
    stopped: 'gestoppt',
  },
}

export default de
