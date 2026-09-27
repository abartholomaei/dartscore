import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { GameMode } from '../api'
import styles from './RulesDialog.module.css'

const SECTIONS = ['goal', 'play', 'scoring', 'win', 'example'] as const

/** The rules of a game mode (goal, how to play, scoring, winning, an example). */
export default function RulesDialog({ mode, onClose }: { mode: GameMode; onClose: () => void }) {
  const { t } = useTranslation()
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    dialog.current?.showModal()
  }, [])
  return (
    <dialog
      ref={dialog}
      className={styles.dialog}
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && dialog.current?.close()}
    >
      <div className={styles.header}>
        <h2>
          {t('rules.title')}: {t(`modes.${mode}`)}
        </h2>
        <button className="button" onClick={() => dialog.current?.close()} aria-label={t('common.close')}>
          ✕
        </button>
      </div>
      <dl className={styles.sections}>
        {SECTIONS.map((section) => (
          <div key={section} className={section === 'example' ? styles.example : undefined}>
            <dt>{t(`rules.${section}`)}</dt>
            <dd>{t(`rules.modes.${mode}.${section}`)}</dd>
          </div>
        ))}
      </dl>
    </dialog>
  )
}

/** Small "?" button that opens the rules. */
export function RulesButton({ mode, onOpen }: { mode: GameMode; onOpen: (mode: GameMode) => void }) {
  const { t } = useTranslation()
  return (
    <button type="button" className={styles.open} onClick={() => onOpen(mode)} title={t('rules.title')}>
      ? {t('rules.open')}
    </button>
  )
}
