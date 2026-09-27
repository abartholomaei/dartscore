import { useEffect, useState } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { getJson, sendJson, type GameMode, type GameState } from '../api'
import { useErrorText } from '../helpers'
import { useLiveGame } from '../LiveGame'
import styles from './TrainingPlan.module.css'

type Drill = {
  mode: GameMode
  settings: Record<string, string | number | boolean>
  goal: number
  best?: number | null
  achieved?: boolean
  played?: number
}
type Plan = { id: number; plan: string; status: string; current_session: number; sessions: Drill[][] }
type Catalog = { key: string; sessions: Drill[][] }[]

const PLAN_KEYS = ['doubles_week', 'scoring', 'finishing', 'allround'] as const
type PlanKey = (typeof PLAN_KEYS)[number]

/** A player's training plan: choose one, then play its drills session by session. */
export default function TrainingPlan({ playerId }: { playerId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const errorText = useErrorText()
  const { game, setGame } = useLiveGame()
  const [plan, setPlan] = useState<Plan | null | undefined>(undefined)
  const [catalog, setCatalog] = useState<Catalog>([])
  const [choosing, setChoosing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getJson<Plan | null>(`/api/players/${playerId}/training-plan`).then(setPlan)
    void getJson<Catalog>('/api/training-plans').then(setCatalog)
  }, [playerId])

  const choose = async (key: PlanKey) => {
    setPlan(await sendJson<Plan>('PUT', `/api/players/${playerId}/training-plan`, { plan: key }))
    setChoosing(false)
  }
  const stop = async () => {
    if (!window.confirm(t('plans.confirmStop'))) return
    await sendJson('DELETE', `/api/players/${playerId}/training-plan`)
    setPlan(null)
  }
  const start = async (session: number, drill: number) => {
    setError(null)
    try {
      setGame(await sendJson<GameState>('POST', `/api/players/${playerId}/training-plan/sessions/${session}/drills/${drill}/start`))
      void navigate('/play')
    } catch (err) {
      setError(errorText(err))
    }
  }
  const busy = game !== null && !game.finished
  const describe = (d: Drill) => settingsText(t, d)

  if (plan === undefined) return null
  if (!plan || choosing) {
    return (
      <section className="card">
        <h2 className="cardTitle">{t('plans.title')}</h2>
        <p className="muted">{t('plans.intro')}</p>
        <div className={styles.catalog}>
          {catalog.map((c) => {
            const key = c.key as PlanKey
            return (
              <button key={key} className={`card ${styles.planCard}`} onClick={() => void choose(key)}>
                <strong>{t(`plans.names.${key}`)}</strong>
                <span className="muted">{t(`plans.descriptions.${key}`)}</span>
                <span className={styles.meta}>{t('plans.sessions', { count: c.sessions.length })}</span>
              </button>
            )
          })}
        </div>
        {choosing && (
          <button className="button" onClick={() => setChoosing(false)}>
            {t('common.cancel')}
          </button>
        )}
      </section>
    )
  }

  const key = plan.plan as PlanKey
  const finished = plan.current_session >= plan.sessions.length
  return (
    <section className="card">
      <div className={styles.header}>
        <h2 className="cardTitle">
          {t('plans.title')}: {t(`plans.names.${key}`)}
        </h2>
        <span className="muted">
          {finished ? t('plans.done') : t('plans.progress', { session: plan.current_session + 1, total: plan.sessions.length })}
        </span>
      </div>
      <ol className={styles.sessions}>
        {plan.sessions.map((drills, s) => {
          const open = s <= plan.current_session
          return (
            <li key={s} className={s === plan.current_session ? styles.current : !open ? styles.locked : undefined}>
              <span className={styles.sessionTitle}>{t('plans.session', { n: s + 1 })}</span>
              <ul className={styles.drills}>
                {drills.map((d, i) => (
                  <li key={i} className={styles.drill}>
                    <span className={d.achieved ? styles.check : styles.open}>{d.achieved ? '✓' : d.played ? '✗' : '○'}</span>
                    <span className={styles.drillText}>
                      <strong>{t(`modes.${d.mode}`)}</strong> <span className="muted">{describe(d)}</span>
                      <br />
                      <span className={styles.goal}>
                        {t('plans.goal', { goal: d.goal, unit: t(`plans.units.${unitOf(d.mode)}`) })}
                        {d.best !== null && d.best !== undefined && ` · ${t('plans.best', { best: d.best })}`}
                      </span>
                    </span>
                    {open && (
                      <button className={d.played ? 'button' : 'button primary'} disabled={busy} onClick={() => void start(s, i)}>
                        {d.played ? t('plans.again') : t('plans.start')}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          )
        })}
      </ol>
      {busy && <p className="muted">{t('tournaments.busy')}</p>}
      {error && <p className="error">{error}</p>}
      <div className={styles.actions}>
        <button className="button" onClick={() => setChoosing(true)}>
          {t('plans.change')}
        </button>
        <button className="button danger" onClick={() => void stop()}>
          {t('plans.stop')}
        </button>
      </div>
    </section>
  )
}

type Unit = 'fields' | 'points' | 'checkouts' | 'hits' | 'target'

function unitOf(mode: GameMode): Unit {
  switch (mode) {
    case 'around_the_clock':
      return 'fields'
    case 'checkout_training':
      return 'checkouts'
    case 'doubles_training':
    case 'segment_training':
      return 'hits'
    case 'checkout_121':
      return 'target'
    default:
      return 'points'
  }
}

function settingsText(t: TFunction, d: Drill): string {
  const s = d.settings
  switch (d.mode) {
    case 'segment_training': {
      const ring = { any: '', single: 'S', double: 'D', triple: 'T' }[String(s.ring)] ?? ''
      const target = Number(s.number) === 0 ? t('newGame.randomTarget') : Number(s.number) === 25 ? 'Bull' : `${ring}${s.number}`
      return `${target} · ${t('plans.darts', { count: Number(s.limit) })}`
    }
    case 'checkout_training':
      return `${s.min_score}–${s.max_score} · ${t('plans.dartsEach', { count: Number(s.darts_per_target) })}`
    case 'score_training':
      return t('plans.rounds', { count: Number(s.rounds) })
    case 'shanghai':
      return t('plans.rounds', { count: Number(s.rounds) })
    case 'checkout_121':
      return t('plans.attempts', { count: Number(s.attempts) })
    case 'halve_it':
      return s.targets === 'bermuda' ? 'Bermuda' : ''
    case 'doubles_training':
      return s.order === 'random' ? t('newGame.orders.random') : t('newGame.orders.sequential')
    case 'around_the_clock':
      return s.variant === 'double' ? t('newGame.rings.double') : ''
    default:
      return ''
  }
}
