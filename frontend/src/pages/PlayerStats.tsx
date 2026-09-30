import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import {
  ACHIEVEMENT_ICONS,
  getJson,
  type Achievement,
  PARTY_MODES,
  TRAINING_MODES,
  type AggregateStats,
  type HeadToHead,
  type Player,
  type PlayerStats as Stats,
} from '../api'
import Avatar from '../components/Avatar'
import DartBoard from '../components/DartBoard'
import TrainingPlan from '../components/TrainingPlan'
import { useErrorText } from '../helpers'
import styles from './PlayerStats.module.css'

type AimSummary = { darts: number; radial_mm: number; sideways_mm: number; distance_mm: number; points: [number, number][] }
type AimStats = { overall: AimSummary | null; targets: Record<string, AimSummary> }

type Grouping = { turns: number; average_mm: number | null; recent_mm: number | null; best_mm: number | null }

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
  const [positions, setPositions] = useState<[number, number][]>([])
  const [days, setDays] = useState<number | null>(null)
  const [grouping, setGrouping] = useState<Grouping | null>(null)
  const [aim, setAim] = useState<AimStats | null>(null)
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [doubles, setDoubles] = useState<Record<string, { attempts: number; hits: number }>>({})

  useEffect(() => {
    const query = days ? `?days=${days}` : ''
    getJson<Stats>(`/api/stats/players/${id}${query}`)
      .then(setStats)
      .catch((err: unknown) => setError(errorText(err)))
    getJson<Record<string, { attempts: number; hits: number }>>(`/api/stats/players/${id}/doubles${query}`)
      .then(setDoubles)
      .catch(() => undefined)
    getJson<[number, number, string][]>(`/api/stats/players/${id}/positions`)
      .then((list) => setPositions(list.map(([x, y]) => [x, y])))
      .catch(() => undefined)
    getJson<AimStats>(`/api/stats/players/${id}/aim${query}`)
      .then(setAim)
      .catch(() => undefined)
    getJson<Grouping>(`/api/stats/players/${id}/grouping`)
      .then(setGrouping)
      .catch(() => undefined)
    getJson<Achievement[]>(`/api/stats/players/${id}/achievements`)
      .then(setAchievements)
      .catch(() => undefined)
    getJson<Player[]>('/api/players?include_archived=true')
      .then((list) => setOthers(list.filter((p) => String(p.id) !== id)))
      .catch(() => undefined)
  }, [id, days, errorText])

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
        <Avatar name={stats.player.name} color={stats.player.color} avatar={stats.player.avatar} size={64} />
        <h1 className={styles.title}>{stats.player.name}</h1>
        <select
          className={styles.select}
          aria-label={t('stats.period')}
          value={days ?? ''}
          onChange={(e) => setDays(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t('stats.allTime')}</option>
          {[7, 30, 90, 365].map((d) => (
            <option key={d} value={d}>
              {t('stats.lastDays', { count: d })}
            </option>
          ))}
        </select>
        <Link to="/players" className="button">
          {t('nav.players')}
        </Link>
      </div>

      {Object.keys(stats.modes).length === 0 && <p className="muted">{t('stats.noGames')}</p>}

      <TrainingPlan playerId={stats.player.id} />

      {others.length > 0 && (
        <section className="card">
          <div className={styles.h2hTop}>
            <h2 className="cardTitle">{t('stats.headToHead')}</h2>
            <select
              className={styles.select}
              aria-label={t('stats.chooseOpponent')}
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
          </div>
          {h2h && opponent !== null && (
            <HeadToHeadView
              h2h={h2h}
              me={{ id: stats.player.id, name: stats.player.name, color: stats.player.color, avatar: stats.player.avatar }}
              them={others.find((p) => p.id === opponent)}
            />
          )}
        </section>
      )}

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
          <VisitDistribution stats={x01} />
          <FormAndGames stats={x01} />
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

      {[...TRAINING_MODES, ...PARTY_MODES].filter((m) => stats.modes[m]).map((m) => {
        const ms = stats.modes[m] as AggregateStats
        return (
          <section key={m} className="card">
            <h2 className="cardTitle">{t(`modes.${m}`)}</h2>
            <div className={styles.tiles}>
              <Tile label={t('stats.bestScore')} value={ms.best_score ?? '–'} big />
              <Tile label={t('stats.averageScore')} value={num(ms.average_score)} />
              <Tile label={t('play.stats.hitRate')} value={pct(ms.hit_rate)} />
              <Tile label={t('stats.gamesPlayed')} value={ms.games} />
            </div>
            <Trend stats={ms} field="score" label={t('stats.scoreTrend')} />
          </section>
        )
      })}

      {aim?.overall && <AimCard aim={aim} />}

      {achievements.length > 0 && <Achievements items={achievements} />}

      {Object.keys(doubles).length > 0 && (
        <section className="card">
          <h2 className="cardTitle">{t('stats.doubles')}</h2>
          <div className={styles.doubles}>
            {[...Array.from({ length: 20 }, (_, i) => i + 1), 25]
              .filter((n) => doubles[String(n)])
              .map((n) => {
                const { attempts, hits } = doubles[String(n)]
                const rate = attempts ? hits / attempts : 0
                return (
                  <div key={n} className={styles.double}>
                    <span className={styles.doubleName}>{n === 25 ? 'Bull' : `D${n}`}</span>
                    <span className={styles.bar}>
                      <span style={{ width: `${Math.round(rate * 100)}%` }} />
                    </span>
                    <span className={styles.doubleValue}>
                      {Math.round(rate * 100)} % <span className="muted">({hits}/{attempts})</span>
                    </span>
                  </div>
                )
              })}
          </div>
          <p className="muted">{t('stats.doublesHint')}</p>
        </section>
      )}

      {positions.length > 0 && (
        <section className="card">
          <h2 className="cardTitle">{t('stats.heatmap', { count: positions.length })}</h2>
          {grouping && grouping.turns > 0 && (
            <>
              <div className={styles.tiles}>
                <Tile label={t('stats.grouping')} value={`${num(grouping.average_mm, 0)} mm`} />
                <Tile label={t('stats.groupingRecent')} value={`${num(grouping.recent_mm, 0)} mm`} />
                <Tile label={t('stats.groupingBest')} value={`${num(grouping.best_mm, 0)} mm`} />
                <Tile label={t('stats.groupingTurns')} value={grouping.turns} />
              </div>
              <p className="muted">{t('stats.groupingHint')}</p>
            </>
          )}
          <div className={styles.heatmap}>
            <DartBoard points={positions} />
          </div>
        </section>
      )}

    </>
  )
}

type Side = { id: number; name: string; color: string; avatar: string | null }

/** Two players side by side like a broadcast graphic: this player in green, the opponent in amber. */
function HeadToHeadView({ h2h, me, them }: { h2h: HeadToHead; me: Side; them: Side | undefined }) {
  const { t } = useTranslation()
  if (!them) return null
  const a = h2h.stats[String(me.id)]
  const b = h2h.stats[String(them.id)]
  const winsA = h2h.wins[String(me.id)] ?? 0
  const winsB = h2h.wins[String(them.id)] ?? 0
  if (!h2h.games || !a || !b) return <p className="muted">{t('stats.gamesCount', { count: 0 })}</p>

  const tons = (s: AggregateStats) => s.tons['100'] + s.tons['140'] + s.tons['180']
  const rows = (
    [
      ['play.stats.average', a.average, b.average, (v: number) => v.toFixed(1)],
      ['play.stats.first9', a.first9_average, b.first9_average, (v: number) => v.toFixed(1)],
      ['play.stats.checkout', a.checkout_rate, b.checkout_rate, (v: number) => pct(v)],
      ['play.stats.highestFinish', a.highest_finish || null, b.highest_finish || null, String],
      ['play.stats.hundredPlus', a.turns ? tons(a) : null, b.turns ? tons(b) : null, String],
      ['stats.oneEighty', a.turns ? a.tons['180'] : null, b.turns ? b.tons['180'] : null, String],
      // MPR only when they played Cricket against each other
      ['play.stats.mpr', a.mpr || null, b.mpr || null, (v: number) => v.toFixed(2)],
    ] as const
  ).filter(([, va, vb]) => va !== null || vb !== null)

  // who won each common game, oldest first
  const wonByMe = new Map(a.trend.map((g) => [g.game_id, g.won]))
  const wonByThem = new Map(b.trend.map((g) => [g.game_id, g.won]))
  const duels = a.trend.map((g) => (wonByMe.get(g.game_id) ? 'me' : wonByThem.get(g.game_id) ? 'them' : 'none')).slice(-12)

  const avgA = a.trend.map((g) => g.average)
  const avgB = b.trend.map((g) => g.average)
  const values = [...avgA, ...avgB].filter((v): v is number => v !== null)

  const side = (p: Side, color: string, wins: number) => (
    <div className={styles.h2hPlayer}>
      <span className={styles.h2hRing} style={{ borderColor: color }}>
        <Avatar name={p.name} color={p.color} avatar={p.avatar} size={112} />
      </span>
      <span className={`broadcast ${styles.h2hName}`}>{p.name}</span>
      <span className="muted">{t('stats.winsCount', { count: wins })}</span>
    </div>
  )

  return (
    <div className={styles.h2hView}>
      <div className={styles.h2hBand}>
        <span className={styles.h2hWedgeLeft} aria-hidden="true" />
        <span className={styles.h2hWedgeRight} aria-hidden="true" />
        {side(me, 'var(--accent)', winsA)}
        <div className={styles.h2hCenter}>
          <span className="label">{t('stats.h2hWins')}</span>
          <span className={`broadcast ${styles.h2hScore}`}>
            <span style={{ color: 'var(--accent)' }}>{winsA}</span>
            <span className={styles.h2hColon}>:</span>
            <span style={{ color: 'var(--opponent)' }}>{winsB}</span>
          </span>
          <span className="muted">{t('stats.gamesCount', { count: h2h.games })}</span>
        </div>
        {side(them, 'var(--opponent)', winsB)}
      </div>

      <div className={styles.h2hBody}>
        <div className={styles.h2hCompare}>
          <h3 className={styles.subTitle}>{t('stats.h2hCompare')}</h3>
          {rows.map(([key, va, vb, format]) => {
            const total = (va ?? 0) + (vb ?? 0)
            const share = total > 0 ? ((va ?? 0) / total) * 100 : 50
            return (
              <div key={key} className={styles.h2hRow}>
                <div className={styles.h2hValues}>
                  <span className="broadcast" style={{ color: (va ?? 0) > (vb ?? 0) ? 'var(--accent)' : undefined }}>
                    {va === null ? '–' : format(va)}
                  </span>
                  <span className="label">{t(key)}</span>
                  <span className="broadcast" style={{ color: (vb ?? 0) > (va ?? 0) ? 'var(--opponent)' : undefined }}>
                    {vb === null ? '–' : format(vb)}
                  </span>
                </div>
                <div className={styles.h2hBar} aria-hidden="true">
                  <span style={{ width: `${share}%` }} />
                  <span />
                </div>
              </div>
            )
          })}
        </div>

        <div className={styles.h2hSide}>
          <h3 className={styles.subTitle}>{t('stats.h2hHistory')}</h3>
          <ol className={styles.duels}>
            {duels.map((who, i) => (
              <li key={i} className={`${styles.duel} ${who === 'me' ? styles.duelMe : who === 'them' ? styles.duelThem : ''}`}>
                <span className="broadcast">{who === 'me' ? me.name : who === 'them' ? them.name : '–'}</span>
              </li>
            ))}
          </ol>
          {values.length >= 2 && (
            <>
              <h3 className={styles.subTitle}>{t('stats.h2hAverage')}</h3>
              <DuelChart a={avgA} b={avgB} label={t('stats.h2hAverage')} />
              <div className={styles.legend}>
                <span>
                  <span className={styles.legendMe} /> {me.name}
                </span>
                <span>
                  <span className={styles.legendThem} /> {them.name}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** Both players' averages per common game on one scale. */
function DuelChart({ a, b, label }: { a: (number | null)[]; b: (number | null)[]; label: string }) {
  const values = [...a, ...b].filter((v): v is number => v !== null)
  const w = 600
  const h = 160
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  const n = Math.max(a.length, b.length)
  const line = (series: (number | null)[]) =>
    series
      .map((v, i) => (v === null ? null : [n > 1 ? (i / (n - 1)) * w : w / 2, h - ((v - min) / span) * (h - 16) - 8]))
      .filter((p): p is number[] => p !== null)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label} className={styles.duelChart}>
      <polyline points={line(b).map(([x, y]) => `${x},${y}`).join(' ')} className={styles.lineThem} />
      <polyline points={line(a).map(([x, y]) => `${x},${y}`).join(' ')} className={styles.lineMe} />
    </svg>
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
function Trend({ stats, field, label }: { stats: AggregateStats; field: 'average' | 'mpr' | 'score'; label: string }) {
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

function Achievements({ items }: { items: Achievement[] }) {
  const { t, i18n } = useTranslation()
  const unlocked = items.filter((a) => a.achieved_at).length
  return (
    <section className="card">
      <h2 className="cardTitle">
        {t('achievements.title')} <span className="muted">{t('achievements.count', { count: unlocked, total: items.length })}</span>
      </h2>
      <ul className={styles.achievements}>
        {items.map((a) => (
          <li
            key={a.id}
            className={a.achieved_at ? styles.achievement : `${styles.achievement} ${styles.locked}`}
            title={t(`achievements.items.${a.id}.description`)}
          >
            <span className={styles.achievementIcon} aria-hidden>
              {ACHIEVEMENT_ICONS[a.id]}
            </span>
            <span className={styles.achievementText}>
              <strong>{t(`achievements.items.${a.id}.name`)}</strong>
              <span className="muted">
                {a.achieved_at
                  ? new Date(a.achieved_at).toLocaleDateString(i18n.language)
                  : t(`achievements.items.${a.id}.description`)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Where the darts land relative to the intended field (T20 while scoring, doubles on a finish,
 *  training targets). "radial" = towards the board edge, "sideways" = clockwise. */
function AimCard({ aim }: { aim: AimStats }) {
  const { t } = useTranslation()
  const names = Object.keys(aim.targets).sort((a, b) => aim.targets[b].darts - aim.targets[a].darts)
  const [selected, setSelected] = useState(names[0] ?? '')
  const summary = aim.targets[selected] ?? aim.overall
  if (!summary) return null
  const t20 = selected === 'T20'
  const vertical =
    Math.abs(summary.radial_mm) < 1
      ? t('aim.centered')
      : t(t20 ? (summary.radial_mm > 0 ? 'aim.high' : 'aim.low') : summary.radial_mm > 0 ? 'aim.outside' : 'aim.inside', {
          mm: Math.abs(summary.radial_mm).toFixed(1),
        })
  const horizontal =
    Math.abs(summary.sideways_mm) < 1
      ? t('aim.centered')
      : t(t20 ? (summary.sideways_mm > 0 ? 'aim.right' : 'aim.left') : summary.sideways_mm > 0 ? 'aim.clockwise' : 'aim.counterclockwise', {
          mm: Math.abs(summary.sideways_mm).toFixed(1),
        })
  const range = 40 // mm shown around the target
  return (
    <section className="card">
      <h2 className="cardTitle">{t('aim.title')}</h2>
      <div className={styles.aimTabs}>
        {names.map((name) => (
          <button
            key={name}
            className={name === selected ? `${styles.aimTab} ${styles.aimTabActive}` : styles.aimTab}
            onClick={() => setSelected(name)}
          >
            {name === 'doubles' ? t('aim.doubles') : name} <span className="muted">({aim.targets[name].darts})</span>
          </button>
        ))}
      </div>
      <div className={styles.aim}>
        <svg viewBox={`${-range} ${-range} ${2 * range} ${2 * range}`} className={styles.aimPlot} aria-hidden>
          {[10, 20, 30].map((r) => (
            <circle key={r} r={r} className={styles.aimRing} />
          ))}
          <line x1={-range} x2={range} y1={0} y2={0} className={styles.aimAxis} />
          <line y1={-range} y2={range} x1={0} x2={0} className={styles.aimAxis} />
          {summary.points.map(([radial, sideways], i) => (
            <circle key={i} cx={sideways} cy={-radial} r={1.4} className={styles.aimPoint} />
          ))}
          <circle cx={summary.sideways_mm} cy={-summary.radial_mm} r={2.6} className={styles.aimMean} />
        </svg>
        <div className={styles.tiles}>
          <Tile label={t(t20 ? 'aim.vertical' : 'aim.radial')} value={vertical} />
          <Tile label={t(t20 ? 'aim.horizontal' : 'aim.sideways')} value={horizontal} />
          <Tile label={t('aim.distance')} value={`${summary.distance_mm.toFixed(1)} mm`} />
          <Tile label={t('aim.darts')} value={summary.darts} />
        </div>
      </div>
      <p className="muted">{t(t20 ? 'aim.hintT20' : 'aim.hint')}</p>
    </section>
  )
}

/** How the X01 visits are spread over score ranges (busts count as 0). */
function VisitDistribution({ stats }: { stats: AggregateStats }) {
  const { t } = useTranslation()
  const tons = stats.tons
  const scored = tons['60'] + tons['100'] + tons['140'] + tons['180']
  const buckets = [
    { label: '0–59', count: Math.max(0, stats.turns - scored) },
    { label: '60+', count: tons['60'] },
    { label: '100+', count: tons['100'] },
    { label: '140+', count: tons['140'] },
    { label: '180', count: tons['180'] },
  ]
  if (!stats.turns) return null
  const max = Math.max(...buckets.map((b) => b.count), 1)
  return (
    <div className={styles.distribution}>
      <h3 className={styles.subTitle}>{t('stats.visitDistribution', { count: stats.turns })}</h3>
      {buckets.map((b) => (
        <div key={b.label} className={styles.double}>
          <span className={styles.doubleName}>{b.label}</span>
          <span className={styles.bar}>
            <span style={{ width: `${Math.round((b.count / max) * 100)}%` }} />
          </span>
          <span className={styles.doubleValue}>
            {Math.round((b.count / stats.turns) * 100)} % <span className="muted">({b.count})</span>
          </span>
        </div>
      ))}
    </div>
  )
}

/** Recent form (last 5 games against the overall average) and the best and worst games. */
function FormAndGames({ stats }: { stats: AggregateStats }) {
  const { t, i18n } = useTranslation()
  const games = stats.trend.filter((g) => g.average !== null) as (AggregateStats['trend'][number] & { average: number })[]
  if (games.length < 2 || stats.average === null) return null
  const recent = games.slice(-5)
  const form = recent.reduce((sum, g) => sum + g.average, 0) / recent.length
  const delta = form - stats.average
  const sorted = [...games].sort((a, b) => b.average - a.average)
  const best = sorted.slice(0, 3)
  const worst = sorted.slice(-3).reverse().filter((g) => !best.includes(g))
  const date = (iso: string) => new Date(iso).toLocaleDateString(i18n.language)
  const arrow = delta > 1 ? '▲' : delta < -1 ? '▼' : '▬'
  return (
    <div className={styles.form}>
      <div className={styles.tiles}>
        <div className={`${styles.tile} ${delta > 1 ? styles.formUp : delta < -1 ? styles.formDown : ''}`}>
          <span className={styles.tileValue}>
            {arrow} {form.toFixed(1)}
          </span>
          <span className={styles.tileLabel}>
            {t('stats.form', { count: recent.length })} ({delta >= 0 ? '+' : ''}
            {delta.toFixed(1)})
          </span>
        </div>
      </div>
      <div className={styles.gameLists}>
        <div>
          <h3 className={styles.subTitle}>{t('stats.bestGames')}</h3>
          <ol className={styles.gameList}>
            {best.map((g) => (
              <li key={g.game_id}>
                <strong>{g.average.toFixed(1)}</strong> <span className="muted">{date(g.date)}</span>
              </li>
            ))}
          </ol>
        </div>
        {worst.length > 0 && (
          <div>
            <h3 className={styles.subTitle}>{t('stats.worstGames')}</h3>
            <ol className={styles.gameList}>
              {worst.map((g) => (
                <li key={g.game_id}>
                  <strong>{g.average.toFixed(1)}</strong> <span className="muted">{date(g.date)}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  )
}
