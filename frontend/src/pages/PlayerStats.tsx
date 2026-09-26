import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { getJson, type AggregateStats, type HeadToHead, type Player, type PlayerStats as Stats } from '../api'
import { useErrorText } from '../helpers'
import styles from './PlayerStats.module.css'

const pct = (v: number | null) => (v === null ? '–' : `${Math.round(v * 1000) / 10} %`)
const num = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? '–' : v.toFixed(digits))

export default function PlayerStats() {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const { id } = useParams()
  const [stats, setStats] = useState<Stats | null>(null)
  const [others, setOthers] = useState<Player[]>([])
  const [opponent, setOpponent] = useState<number | null>(null)
  const [h2h, setH2h] = useState<HeadToHead | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getJson<Stats>(`/api/stats/players/${id}`)
      .then(setStats)
      .catch((err: unknown) => setError(errorText(err)))
    getJson<Player[]>('/api/players?include_archived=true')
      .then((list) => setOthers(list.filter((p) => String(p.id) !== id)))
      .catch(() => undefined)
  }, [id, errorText])

  useEffect(() => {
    if (opponent === null) return
    getJson<HeadToHead>(`/api/stats/head-to-head?a=${id}&b=${opponent}`)
      .then(setH2h)
      .catch(() => undefined)
  }, [id, opponent])

  if (error) return <p className="error">{error}</p>
  if (!stats) return <p className="muted">{t('cameras.loading')}</p>

  const x01 = stats.modes.x01
  const cricket = stats.modes.cricket

  return (
    <>
      <div className={styles.header}>
        <span className={styles.avatar} style={{ background: stats.player.color }}>
          {stats.player.name.slice(0, 1).toUpperCase()}
        </span>
        <h1 className={styles.title}>{stats.player.name}</h1>
        <Link to="/players" className="button">
          {t('nav.players')}
        </Link>
      </div>

      {!x01 && !cricket && <p className="muted">{t('stats.noGames')}</p>}

      {x01 && (
        <section className="card">
          <h2 className="cardTitle">X01</h2>
          <div className={styles.tiles}>
            <Tile label={t('play.stats.average')} value={num(x01.average, 2)} big />
            <Tile label={t('play.stats.first9')} value={num(x01.first9_average, 2)} />
            <Tile label={t('play.stats.checkout')} value={pct(x01.checkout_rate)} />
            <Tile label={t('play.stats.highestFinish')} value={x01.highest_finish || '–'} />
            <Tile label={t('play.stats.bestLeg')} value={x01.best_leg_darts ?? '–'} />
            <Tile label={t('stats.dartsPerLeg')} value={num(x01.darts_per_leg)} />
            <Tile label="60+" value={x01.tons['60']} />
            <Tile label="100+" value={x01.tons['100']} />
            <Tile label="140+" value={x01.tons['140']} />
            <Tile label="180" value={x01.tons['180']} />
            <Tile label={t('stats.games')} value={`${x01.wins} / ${x01.games}`} />
            <Tile label={t('stats.winRate')} value={pct(x01.win_rate)} />
          </div>
          <Trend stats={x01} field="average" label={t('stats.averageTrend')} />
        </section>
      )}

      {cricket && (
        <section className="card">
          <h2 className="cardTitle">Cricket</h2>
          <div className={styles.tiles}>
            <Tile label={t('play.stats.mpr')} value={num(cricket.mpr, 2)} big />
            <Tile label={t('play.stats.marks')} value={cricket.marks} />
            <Tile label={t('stats.games')} value={`${cricket.wins} / ${cricket.games}`} />
            <Tile label={t('stats.winRate')} value={pct(cricket.win_rate)} />
          </div>
          <Trend stats={cricket} field="mpr" label={t('stats.mprTrend')} />
        </section>
      )}

      {others.length > 0 && (
        <section className="card">
          <h2 className="cardTitle">{t('stats.headToHead')}</h2>
          <select
            className={styles.select}
            value={opponent ?? ''}
            onChange={(e) => setOpponent(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('stats.chooseOpponent')}</option>
            {others.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {h2h && opponent !== null && (
            <div className={styles.h2h}>
              <span className={styles.h2hScore}>
                {h2h.wins[String(id)] ?? 0} : {h2h.wins[String(opponent)] ?? 0}
              </span>
              <span className="muted">{t('stats.gamesCount', { count: h2h.games })}</span>
            </div>
          )}
        </section>
      )}
    </>
  )
}

function Tile({ label, value, big }: { label: string; value: string | number; big?: boolean }) {
  return (
    <div className={`${styles.tile} ${big ? styles.big : ''}`}>
      <span className={styles.tileValue}>{value}</span>
      <span className={styles.tileLabel}>{label}</span>
    </div>
  )
}

/** Small line chart of the per-game value over time. */
function Trend({ stats, field, label }: { stats: AggregateStats; field: 'average' | 'mpr'; label: string }) {
  const points = stats.trend.map((p) => p[field]).filter((v): v is number => v !== null)
  if (points.length < 2) return null
  const w = 600
  const h = 120
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const coords = points.map((v, i) => [(i / (points.length - 1)) * w, h - ((v - min) / span) * (h - 16) - 8])
  return (
    <figure className={styles.trend}>
      <figcaption className="muted">
        {label} ({min.toFixed(1)} – {max.toFixed(1)})
      </figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label}>
        <polyline points={coords.map(([x, y]) => `${x},${y}`).join(' ')} />
        {coords.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={3} />
        ))}
      </svg>
    </figure>
  )
}
