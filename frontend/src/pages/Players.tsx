import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { getJson, sendJson, type Player } from '../api'
import { PLAYER_COLORS, useErrorText } from '../helpers'
import styles from './Players.module.css'

export default function Players() {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const [players, setPlayers] = useState<Player[] | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState<Player | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    getJson<Player[]>(`/api/players?include_archived=${showArchived}`)
      .then(setPlayers)
      .catch((err: unknown) => setError(errorText(err)))
  }, [showArchived, errorText])

  useEffect(reload, [reload])

  const remove = async (player: Player) => {
    if (!window.confirm(t('players.confirmDelete', { name: player.name }))) return
    try {
      await sendJson('DELETE', `/api/players/${player.id}`)
      reload()
    } catch (err) {
      setError(errorText(err))
    }
  }

  const restore = async (player: Player) => {
    try {
      await sendJson('POST', `/api/players/${player.id}/restore`)
      reload()
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <>
      <div className={styles.toolbar}>
        <h1 className={styles.title}>{t('players.title')}</h1>
        <label className={styles.toggle}>
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          {t('players.showArchived')}
        </label>
        <button className="button primary" onClick={() => setEditing('new')}>
          {t('players.add')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {editing && (
        <PlayerForm
          player={editing === 'new' ? null : editing}
          onDone={() => {
            setEditing(null)
            reload()
          }}
        />
      )}
      {players?.length === 0 && <p className="muted">{t('players.empty')}</p>}
      <ul className={styles.list}>
        {players?.map((p) => (
          <li key={p.id} className={`card ${styles.item} ${p.archived ? styles.archived : ''}`}>
            <span className={styles.avatar} style={{ background: p.color }}>
              {p.name.slice(0, 1).toUpperCase()}
            </span>
            <Link to={`/players/${p.id}`} className={styles.name}>
              {p.name}
            </Link>
            {p.archived ? (
              <button className="button" onClick={() => void restore(p)}>
                {t('players.restore')}
              </button>
            ) : (
              <>
                <button className="button" onClick={() => setEditing(p)}>
                  {t('players.edit')}
                </button>
                <button className="button danger" onClick={() => void remove(p)}>
                  {t('players.delete')}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

export function PlayerForm({ player, onDone }: { player: Player | null; onDone: (p?: Player) => void }) {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const [name, setName] = useState(player?.name ?? '')
  const [color, setColor] = useState(
    () => player?.color ?? PLAYER_COLORS[Math.floor(Math.random() * PLAYER_COLORS.length)],
  )
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const saved = player
        ? await sendJson<Player>('PATCH', `/api/players/${player.id}`, { name, color })
        : await sendJson<Player>('POST', '/api/players', { name, color })
      onDone(saved)
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <form className={`card ${styles.form}`} onSubmit={(e) => void submit(e)}>
      <label className={styles.field}>
        {t('players.name')}
        <input value={name} maxLength={40} required autoFocus onChange={(e) => setName(e.target.value)} />
      </label>
      <div className={styles.field}>
        {t('players.color')}
        <div className={styles.colors}>
          {PLAYER_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              className={c === color ? `${styles.swatch} ${styles.swatchActive}` : styles.swatch}
              style={{ background: c }}
              aria-label={c}
              aria-pressed={c === color}
              onClick={() => setColor(c)}
            />
          ))}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <div className={styles.formActions}>
        <button type="button" className="button" onClick={() => onDone()}>
          {t('common.cancel')}
        </button>
        <button type="submit" className="button primary">
          {t('common.save')}
        </button>
      </div>
    </form>
  )
}
