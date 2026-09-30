import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { getJson, type GameMode, type GameState, type HistoryEntry } from '../api'
import { gameTitle, sideColor } from '../helpers'
import { useLiveGame } from '../LiveGame'
import Avatar from '../components/Avatar'
import ConnectQr from '../components/ConnectQr'
import styles from './Home.module.css'

const QUICK: { mode: GameMode; title: string; hint: 'quickX01' | 'quickCricket' | 'quickArcade' }[] = [
  { mode: 'x01', title: 'X01', hint: 'quickX01' },
  { mode: 'cricket', title: 'Cricket', hint: 'quickCricket' },
  { mode: 'monster_hunt', title: 'Arcade', hint: 'quickArcade' },
]

export default function Home() {
  const { t, i18n } = useTranslation()
  const { game } = useLiveGame()
  const [recent, setRecent] = useState<HistoryEntry[]>([])

  useEffect(() => {
    getJson<HistoryEntry[]>('/api/games?limit=8')
      .then(setRecent)
      .catch(() => undefined)
  }, [game?.finished])

  const running = game && !game.finished
  const dateFormat = new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: 'medium', timeStyle: 'short' })

  return (
    <>
      <div className={styles.top}>
        {running ? (
          <MatchCard game={game} />
        ) : (
          <section className={styles.welcome}>
            <h1 className={styles.title}>
              dart<span className={styles.titleAccent}>score</span>
            </h1>
            <div className={styles.welcomeActions}>
              <Link to="/play/new" className="button primary large">
                {t('home.newGame')}
              </Link>
              <Link to="/players" className="button large">
                {t('nav.players')}
              </Link>
            </div>
          </section>
        )}
        <aside className={styles.quick}>
          <h2 className="label">{t('home.quickStart')}</h2>
          {QUICK.map((q, i) => (
            <Link key={q.mode} to={`/play/new?mode=${q.mode}`} className={`${styles.tile} ${i === 0 ? styles.tilePrimary : ''}`}>
              <span className={`broadcast ${styles.tileTitle}`}>{q.title}</span>
              <span className={styles.tileHint}>{t(`home.${q.hint}`)}</span>
              <span className={styles.tileArrow} aria-hidden="true">
                →
              </span>
            </Link>
          ))}
          <Link to="/play/new" className={styles.allModes}>
            {t('home.allModes')} →
          </Link>
        </aside>
      </div>

      {recent.length > 0 && (
        <section className={styles.results}>
          <h2 className="label">{t('home.results')}</h2>
          <ul className={styles.resultGrid}>
            {recent.map((g) => {
              const winner = g.players.find((p) => p.position === g.winner)
              const others = g.players.filter((p) => p !== winner).map((p) => p.name)
              const average = g.mode === 'x01' ? winner?.stats?.average : null
              return (
                <li key={g.id} className={styles.result}>
                  <div className={styles.resultHead}>
                    <span>{gameTitle(t, g.mode, g.settings)}</span>
                    <span>{g.status === 'aborted' ? t('home.aborted') : dateFormat.format(new Date(g.created_at + 'Z'))}</span>
                  </div>
                  {winner ? (
                    <div className={styles.resultBody}>
                      <Avatar name={winner.name} color={winner.color} avatar={winner.avatar} size={44} />
                      <div className={styles.resultNames}>
                        <span className={`broadcast ${styles.resultWinner}`}>{winner.name}</span>
                        {others.length > 0 && (
                          <span className="muted">{t('home.against', { names: others.join(', ') })}</span>
                        )}
                      </div>
                      <span className={`broadcast ${styles.resultValue}`}>
                        {average != null ? average.toFixed(1) : '🏆'}
                      </span>
                    </div>
                  ) : (
                    <div className={styles.resultBody}>
                      <span className="muted">{g.players.map((p) => p.name).join(', ')}</span>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}
      <section className="card">
        <ConnectQr size={120} />
      </section>
    </>
  )
}

/** The running game as a match preview: the players face each other, the legs in between. */
function MatchCard({ game }: { game: GameState }) {
  const { t } = useTranslation()
  const duel = game.players.length === 2
  const legs = Number(game.settings.legs_to_win ?? 1) > 1 || Number(game.settings.sets_to_win ?? 1) > 1
  const detail = (position: number) => {
    const p = game.players[position]
    if (game.mode === 'x01') {
      const avg = p.stats.average
      return `${t('home.left', { score: game.remaining?.[position] ?? '–' })}${avg != null ? ` · Ø ${avg.toFixed(1)}` : ''}`
    }
    if (game.points) return t('home.points', { points: game.points[position] ?? 0 })
    return null
  }
  const player = (position: number) => {
    const p = game.players[position]
    return (
      <div key={position} className={styles.matchPlayer}>
        <span className={styles.ring} style={{ borderColor: sideColor(game.players, position) }}>
          <Avatar name={p.name} color={p.color} avatar={p.avatar} size={duel ? 150 : 84} />
        </span>
        <span className={`broadcast ${duel ? styles.matchName : styles.matchNameSmall}`}>{p.name}</span>
        {detail(position) && <span className="muted">{detail(position)}</span>}
      </div>
    )
  }
  return (
    <Link to="/play" className={styles.match}>
      {duel && (
        <>
          <span className={styles.wedgeLeft} style={{ background: sideColor(game.players, 0) }} aria-hidden="true" />
          <span className={styles.wedgeRight} style={{ background: sideColor(game.players, 1) }} aria-hidden="true" />
        </>
      )}
      <div className={styles.matchHead}>
        <span className={styles.live}>
          <span className={styles.liveDot} aria-hidden="true" />
          {t('home.live')}
        </span>
        <span className="label">
          {t('home.continue')} · {gameTitle(t, game.mode, game.settings)}
          {legs && ` · ${t('play.leg')} ${game.leg}`}
        </span>
      </div>
      {duel ? (
        <div className={styles.duel}>
          {player(0)}
          <div className={styles.versus}>
            {legs ? (
              <>
                <span className="label">{t('home.legs')}</span>
                <span className={`broadcast ${styles.legScore}`}>
                  {game.legs_won[0]}
                  <span className={styles.legColon}>:</span>
                  {game.legs_won[1]}
                </span>
              </>
            ) : (
              <span className={`broadcast ${styles.vs}`}>vs</span>
            )}
          </div>
          {player(1)}
        </div>
      ) : (
        <div className={styles.group}>{game.players.map((p) => player(p.position))}</div>
      )}
      <span className={`button primary large ${styles.matchCta}`}>▶ {t('home.resume')}</span>
    </Link>
  )
}
