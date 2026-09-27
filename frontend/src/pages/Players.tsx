import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ApiError, getJson, sendBlob, sendJson, PARTY_MODES, TRAINING_MODES, type GameMode, type Player } from '../api'
import { PLAYER_COLORS, useErrorText } from '../helpers'
import Avatar from '../components/Avatar'
import AvatarEditor, { type AvatarChange } from '../components/AvatarEditor'
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
      await withPin(t('players.enterPin'), (headers) => sendJson('DELETE', `/api/players/${player.id}`, undefined, headers))
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
            <Avatar name={p.name} color={p.color} avatar={p.avatar} size={44} />
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
  const [favoriteDouble, setFavoriteDouble] = useState<number | null>(player?.favorite_double ?? null)
  const [hand, setHand] = useState<Player['throwing_hand']>(player?.throwing_hand ?? null)
  const [defaultMode, setDefaultMode] = useState<GameMode | null>(player?.default_mode ?? null)
  const [avatarChange, setAvatarChange] = useState<AvatarChange | null>(null)
  const [newPin, setNewPin] = useState('')
  const [removePin, setRemovePin] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const changes: Record<string, unknown> = {
        favorite_double: favoriteDouble,
        throwing_hand: hand,
        default_mode: defaultMode,
      }
      if (newPin) changes.new_pin = newPin
      else if (removePin) changes.new_pin = null
      // the PIN is asked once and reused for the picture
      const pin: { headers?: Record<string, string> } = {}
      let saved = player
        ? await withPin(
            t('players.enterPin'),
            (headers) => sendJson<Player>('PATCH', `/api/players/${player.id}`, { name, color, ...changes }, headers),
            pin,
          )
        : await sendJson<Player>('POST', '/api/players', { name, color }).then((created) =>
            sendJson<Player>('PATCH', `/api/players/${created.id}`, changes),
          )
      if (avatarChange) {
        const path = `/api/players/${saved.id}/avatar`
        const change = avatarChange
        saved = await withPin(
          t('players.enterPin'),
          (headers) =>
            change.kind === 'photo'
              ? sendBlob<Player>('PUT', path, change.blob, headers)
              : change.kind === 'gallery'
                ? sendJson<Player>('PUT', `${path}/gallery`, { name: change.name }, headers)
                : sendJson<Player>('DELETE', path, undefined, headers),
          pin,
        )
      }
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
        {t('avatar.title')}
        <AvatarEditor name={name} color={color} current={player?.avatar ?? null} onChange={setAvatarChange} />
      </div>
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
      <div className={styles.row}>
        <label className={styles.field}>
          {t('players.favoriteDouble')}
          <select
            value={favoriteDouble ?? ''}
            onChange={(e) => setFavoriteDouble(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('players.none')}</option>
            {[...Array.from({ length: 20 }, (_, i) => i + 1), 25].map((n) => (
              <option key={n} value={n}>
                {n === 25 ? 'Bull' : `D${n}`}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          {t('players.hand')}
          <select value={hand ?? ''} onChange={(e) => setHand((e.target.value || null) as Player['throwing_hand'])}>
            <option value="">{t('players.none')}</option>
            <option value="right">{t('players.right')}</option>
            <option value="left">{t('players.left')}</option>
          </select>
        </label>
        <label className={styles.field}>
          {t('players.defaultMode')}
          <select value={defaultMode ?? ''} onChange={(e) => setDefaultMode((e.target.value || null) as GameMode | null)}>
            <option value="">{t('players.none')}</option>
            {(['x01', 'cricket', ...TRAINING_MODES, ...PARTY_MODES] as GameMode[]).map((m) => (
              <option key={m} value={m}>
                {t(`modes.${m}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className={styles.row}>
        <label className={styles.field}>
          {player?.has_pin ? t('players.changePin') : t('players.pin')}
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]{4,8}"
            maxLength={8}
            value={newPin}
            placeholder={t('players.pinPlaceholder')}
            onChange={(e) => setNewPin(e.target.value.replace(/[^0-9]/g, ''))}
          />
        </label>
        {player?.has_pin && (
          <label className={styles.toggle}>
            <input type="checkbox" checked={removePin} onChange={(e) => setRemovePin(e.target.checked)} />
            {t('players.removePin')}
          </label>
        )}
      </div>
      <p className="muted">{t('players.pinHint')}</p>
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

/** Runs a change; if the profile is PIN-protected, asks for the PIN and tries again. */
async function withPin<T>(
  question: string,
  run: (headers?: Record<string, string>) => Promise<T>,
  remembered: { headers?: Record<string, string> } = {},
): Promise<T> {
  try {
    return await run(remembered.headers)
  } catch (err) {
    if (!(err instanceof ApiError) || err.code !== 'pin_required') throw err
    const pin = window.prompt(question)
    if (pin === null) throw err
    remembered.headers = { 'X-Player-Pin': pin }
    return run(remembered.headers)
  }
}
