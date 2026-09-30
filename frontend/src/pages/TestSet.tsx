import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getJson, sendJson, type DetectedDart, type TestScenario, type TestSetSummary } from '../api'
import { useLiveGame } from '../LiveGame'
import styles from './TestSet.module.css'

// the detector counts at most three darts per turn: pull them after the third
const DARTS_PER_TURN = 3
const STORAGE_KEY = 'dartscore.testset.index'

const ALL_FIELDS = [
  ...['S', 'D', 'T'].flatMap((m) => Array.from({ length: 20 }, (_, i) => `${m}${i + 1}`)),
  '25',
  'BULL',
  'MISS',
]

type Phase = 'place' | 'confirm' | 'pull'

function loadIndex(): number {
  try {
    return Number(window.localStorage.getItem(STORAGE_KEY) ?? 0) || 0
  } catch {
    return 0
  }
}

function saveIndex(index: number) {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(index))
  } catch {
    // private window or blocked storage: progress is only kept until reload
  }
}

/**
 * Records a labeled test set: the player places darts by hand in hard scenarios and confirms
 * the field each one is really in. The label is stored next to the dart's recording.
 */
export default function TestSet() {
  const { t } = useTranslation()
  const { lastDart, takeouts, game } = useLiveGame()
  const [scenarios, setScenarios] = useState<TestScenario[] | null>(null)
  const [summary, setSummary] = useState<TestSetSummary | null>(null)
  const [index, setIndex] = useState(loadIndex)
  // the last dart that was labeled or dropped; darts from before this page opened are skipped
  const [handledDart, setHandledDart] = useState(() => lastDart?.time ?? null)
  // darts placed since the takeout with this count; a newer takeout means the board is empty
  const [board, setBoard] = useState({ takeouts, darts: 0 })
  const [other, setOther] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshSummary = () => void getJson<TestSetSummary>('/api/testset/summary').then(setSummary)

  useEffect(() => {
    void getJson<TestScenario[]>('/api/testset/scenarios').then(setScenarios)
    refreshSummary()
  }, [])

  const inBoard = board.takeouts === takeouts ? board.darts : 0
  const scenario = scenarios?.[index] ?? null
  const done = scenarios !== null && index >= scenarios.length
  const gameRunning = game !== null && !game.finished

  // pull after three darts (the detector ignores a fourth); a cluster starts on an empty board
  const clusterStart = scenario?.category === 'cluster' && scenario.side === '1'
  const mustPull = inBoard >= DARTS_PER_TURN || (clusterStart && inBoard > 0)
  const pending: DetectedDart | null =
    !mustPull && lastDart && lastDart.time !== handledDart ? lastDart : null
  const phase: Phase = mustPull ? 'pull' : pending ? 'confirm' : 'place'

  const advance = (placed: boolean) => {
    const next = index + 1
    setIndex(next)
    saveIndex(next)
    if (pending) setHandledDart(pending.time)
    setOther('')
    setBoard({ takeouts, darts: inBoard + (placed ? 1 : 0) })
  }

  const confirm = async (label: string) => {
    if (!pending || !scenario) return
    if (!pending.recording) {
      setError(t('testset.noRecording'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await sendJson('POST', '/api/testset/labels', {
        recording: pending.recording,
        label,
        scenario: scenario.id,
      })
      refreshSummary()
      advance(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const restart = () => {
    setIndex(0)
    saveIndex(0)
  }

  const otherLabel = scenario ? scenario.candidates.find((c) => c !== scenario.target) ?? '' : ''
  // angled and clustered darts need more than the target field
  const extra = scenario
    ? t(`testset.extra.${scenario.category}`, {
        side: t(`testset.side.${scenario.side}`, { defaultValue: scenario.side }),
        defaultValue: '',
      })
    : ''

  return (
    <>
      <h1 className={styles.title}>{t('testset.title')}</h1>
      <p className="muted">{t('testset.intro')}</p>
      {gameRunning && <p className="error">{t('testset.gameRunning')}</p>}

      {scenarios && !done && scenario && (
        <section className={`card ${styles.card}`}>
          <p className="muted">
            {t('testset.progress', { current: index + 1, total: scenarios.length })} ·{' '}
            {t(`testset.category.${scenario.category}`, { defaultValue: scenario.category })}
          </p>

          {phase === 'pull' ? (
            <>
              <p className={styles.big}>{t('testset.pull')}</p>
              <div className={styles.actions}>
                <button onClick={() => setBoard({ takeouts, darts: 0 })}>{t('testset.pulled')}</button>
              </div>
            </>
          ) : phase === 'place' ? (
            <>
              <p className={styles.big}>
                {scenario.category === 'cluster'
                  ? t('testset.placeIn', { target: scenario.target })
                  : t('testset.place', { target: scenario.target, other: otherLabel })}
              </p>
              {extra && <p>{extra}</p>}
              <p className="muted">{t('testset.waiting')}</p>
              <div className={styles.actions}>
                <button onClick={() => advance(false)}>{t('testset.skip')}</button>
              </div>
            </>
          ) : (
            pending && (
              <>
                <p className={styles.big}>{t('testset.detected', { label: pending.label })}</p>
                <p>{t('testset.whichField')}</p>
                <div className={styles.actions}>
                  {scenario.candidates.map((c) => (
                    <button
                      key={c}
                      className={c === pending.label ? styles.primary : undefined}
                      disabled={busy}
                      onClick={() => void confirm(c)}
                    >
                      {c}
                    </button>
                  ))}
                </div>
                <div className={styles.actions}>
                  <select value={other} onChange={(e) => setOther(e.target.value)} aria-label={t('testset.otherField')}>
                    <option value="">{t('testset.otherField')}</option>
                    {ALL_FIELDS.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                  <button disabled={!other || busy} onClick={() => void confirm(other)}>
                    {t('testset.save')}
                  </button>
                  <button disabled={busy} onClick={() => advance(true)}>
                    {t('testset.discard')}
                  </button>
                </div>
              </>
            )
          )}
          {error && <p className="error">{error}</p>}
        </section>
      )}

      {done && (
        <section className={`card ${styles.card}`}>
          <p className={styles.big}>{t('testset.done')}</p>
        </section>
      )}

      <section className={`card ${styles.card}`}>
        <strong>{t('testset.collected', { count: summary?.total ?? 0 })}</strong>
        {summary && summary.total > 0 && (
          <ul className={styles.summary}>
            {Object.entries(summary.per_category).map(([category, n]) => (
              <li key={category}>
                {t(`testset.category.${category}`, { defaultValue: category })}: {n}
              </li>
            ))}
          </ul>
        )}
        <div className={styles.actions}>
          <button onClick={restart}>{t('testset.restart')}</button>
        </div>
      </section>
    </>
  )
}
