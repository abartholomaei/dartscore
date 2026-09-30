import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { sendJson, type CameraStatus, type DetectionStatus, type Health } from '../api'
import ConnectQr from '../components/ConnectQr'
import DetectionBadge from '../components/DetectionBadge'
import { useLiveGame } from '../LiveGame'
import { setAudioPref, speechAvailable, stadiumVoiceAvailable, useAudioPrefs, type CallerVoice } from '../caller'
import { LANGUAGES } from '../i18n'
import { usePolling } from '../usePolling'
import styles from './Settings.module.css'

export default function Settings() {
  const { t, i18n } = useTranslation()
  const health = usePolling<Health>('/api/health', 10000)
  const cameras = usePolling<CameraStatus[]>('/api/cameras', 10000)
  const { detection, setDetection, lastDart } = useLiveGame()
  const audio = useAudioPrefs()
  const synthetic = cameras.kind === 'ok' && cameras.data.some((c) => c.source === 'synthetic')

  const resetDetection = async () => {
    setDetection(await sendJson<DetectionStatus>('POST', '/api/detection/reset'))
  }
  const simulate = (body: Record<string, unknown>) => void sendJson('POST', '/api/simulator', body)

  return (
    <>
      <h1 className={styles.title}>{t('settings.title')}</h1>
      <div className={styles.grid}>
        <Link to="/cameras" className={`card ${styles.link}`}>
          <strong>{t('nav.cameras')}</strong>
          <span className="muted">{t('settings.camerasHint')}</span>
        </Link>
        <Link to="/calibration" className={`card ${styles.link}`}>
          <strong>{t('nav.calibration')}</strong>
          <span className="muted">{t('settings.calibrationHint')}</span>
        </Link>
        <Link to="/diagnostics" className={`card ${styles.link}`}>
          <strong>{t('diagnostics.title')}</strong>
          <span className="muted">{t('diagnostics.linkHint')}</span>
        </Link>
        <Link to="/testset" className={`card ${styles.link}`}>
          <strong>{t('testset.title')}</strong>
          <span className="muted">{t('testset.linkHint')}</span>
        </Link>
        <section className={`card ${styles.link}`}>
          <strong>{t('detection.title')}</strong>
          <span>
            <DetectionBadge />
          </span>
          {detection && !detection.available && <span className="muted">{t('detection.hint.unavailable')}</span>}
          {detection?.available && (
            <span className="muted">{t('detection.cameras', { cameras: detection.cameras.join(', ') })}</span>
          )}
          {lastDart && (
            <span>
              {t('detection.last', {
                label: lastDart.label,
                confidence: Math.round(lastDart.confidence * 100),
              })}
            </span>
          )}
          <div className={styles.languages}>
            <button className="button" onClick={() => void resetDetection()} disabled={!detection?.available}>
              {t('detection.reset')}
            </button>
          </div>
        </section>
        <section className={`card ${styles.link}`}>
          <strong>{t('settings.audio')}</strong>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={audio.caller && speechAvailable}
              disabled={!speechAvailable}
              onChange={(e) => setAudioPref('caller', e.target.checked)}
            />
            {t('settings.caller')}
          </label>
          {stadiumVoiceAvailable() && (
            <label className={styles.check}>
              {t('settings.voice')}
              <select
                value={audio.voice}
                disabled={!audio.caller}
                onChange={(e) => setAudioPref('voice', e.target.value as CallerVoice)}
              >
                <option value="stadium">{t('settings.voiceStadium')}</option>
                <option value="browser">{t('settings.voiceBrowser')}</option>
              </select>
            </label>
          )}
          <label className={styles.check}>
            <input type="checkbox" checked={audio.effects} onChange={(e) => setAudioPref('effects', e.target.checked)} />
            {t('settings.effects')}
          </label>
          <label className={styles.check}>
            <input type="checkbox" checked={audio.intro} onChange={(e) => setAudioPref('intro', e.target.checked)} />
            {t('settings.intro')}
          </label>
          <label className={styles.check}>
            <input type="checkbox" checked={audio.sounds} onChange={(e) => setAudioPref('sounds', e.target.checked)} />
            {t('settings.sounds')}
          </label>
          <span className="muted">{speechAvailable ? t('settings.audioHint') : t('settings.noSpeech')}</span>
        </section>
        <section className={`card ${styles.link}`}>
          <ConnectQr />
        </section>
        {synthetic && (
          <section className={`card ${styles.link}`}>
            <strong>{t('simulator.title')}</strong>
            <span className="muted">{t('simulator.hint')}</span>
            <div className={styles.languages}>
              <button className="button" onClick={() => simulate({ action: 'random' })}>
                {t('simulator.throw')}
              </button>
              <button className="button" onClick={() => simulate({ action: 'hand', on: true })}>
                {t('simulator.handIn')}
              </button>
              <button className="button" onClick={() => simulate({ action: 'clear' })}>
                {t('simulator.clear')}
              </button>
              <button className="button" onClick={() => simulate({ action: 'hand', on: false })}>
                {t('simulator.handOut')}
              </button>
            </div>
          </section>
        )}
        <section className={`card ${styles.link}`}>
          <strong>{t('settings.export')}</strong>
          <span className="muted">{t('settings.exportHint')}</span>
          <div className={styles.languages}>
            <a className="button" href="/api/export/games.csv" download>
              {t('settings.exportGames')}
            </a>
            <a className="button" href="/api/export/darts.csv" download>
              {t('settings.exportDarts')}
            </a>
            <a className="button" href="/api/export/all.json" download>
              JSON
            </a>
          </div>
        </section>
        <section className={`card ${styles.link}`}>
          <strong>{t('language.label')}</strong>
          <div className={styles.languages}>
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                className={i18n.resolvedLanguage === lang.code ? 'button primary' : 'button'}
                onClick={() => void i18n.changeLanguage(lang.code)}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </section>
        <section className={`card ${styles.link}`}>
          <strong>{t('settings.system')}</strong>
          {health.kind === 'ok' ? (
            <span className="muted">
              {t('home.version')} {health.data.version} · {t('home.cameras')}: {health.data.cameras_configured}
            </span>
          ) : health.kind === 'error' ? (
            <span className="error">{t('home.unreachable', { message: health.message })}</span>
          ) : (
            <span className="muted">{t('home.connecting')}</span>
          )}
        </section>
      </div>
    </>
  )
}
