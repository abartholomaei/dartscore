import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { getJson, type HistoryEntry } from '../api'
import { gameTitle } from '../helpers'
import { useLiveGame } from '../LiveGame'
import ConnectQr from '../components/ConnectQr'
import styles from './Home.module.css'

export default function Home() {
  const { t, i18n } = useTranslation()
  const { game } = useLiveGame()
  const [recent, setRecent] = useState<HistoryEntry[]>([])

  useEffect(() => {
    getJson<HistoryEntry[]>('/api/games?limit=6')
      .then(setRecent)
      .catch(() => undefined)
  }, [game?.finished])

  const running = game && !game.finished
  const dateFormat = new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: 'medium', timeStyle: 'short' })

  return (
    <>
      <h1 className={styles.title}>dartscore</h1>
      <div className={styles.hero}>
        {running && (
          <Link to="/play" className={`card ${styles.resume}`}>
            <span className={styles.resumeLabel}>{t('home.continue')}</span>
            <span className={styles.resumeTitle}>{gameTitle(t, game.mode, game.settings)}</span>
            <span className={styles.resumePlayers}>
              {game.players.map((p) => (
                <span key={p.position}>
                  <span className={styles.dot} style={{ background: p.color }} />
                  {p.name}
                  {game.mode === 'x01' && <strong> {game.remaining?.[p.position]}</strong>}
                </span>
              ))}
            </span>
          </Link>
        )}
        <Link to="/play/new" className="button primary large">
          {t('home.newGame')}
        </Link>
        <Link to="/players" className="button large">
          {t('nav.players')}
        </Link>
      </div>

      {recent.length > 0 && (
        <section className="card">
          <h2 className="cardTitle">{t('home.recent')}</h2>
          <ul className={styles.recent}>
            {recent.map((g) => (
              <li key={g.id}>
                <span className={styles.recentTitle}>{gameTitle(t, g.mode, g.settings)}</span>
                <span className={styles.recentPlayers}>
                  {g.players.map((p) => (
                    <span key={p.position} className={p.position === g.winner ? styles.winner : undefined}>
                      {p.position === g.winner && '🏆 '}
                      {p.name}
                      {g.mode === 'x01' && p.stats?.average != null && (
                        <span className="muted"> Ø {p.stats.average.toFixed(1)}</span>
                      )}
                    </span>
                  ))}
                </span>
                <span className="muted">
                  {g.status === 'aborted' ? t('home.aborted') : dateFormat.format(new Date(g.created_at + 'Z'))}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="card">
        <ConnectQr size={120} />
      </section>
    </>
  )
}
