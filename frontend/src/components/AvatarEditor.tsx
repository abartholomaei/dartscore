import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getJson } from '../api'
import Avatar from './Avatar'
import styles from './AvatarEditor.module.css'

export type AvatarChange = { kind: 'photo'; blob: Blob } | { kind: 'gallery'; name: string } | { kind: 'remove' }

const VIEW = 240 // crop window (px)
const OUTPUT = 512 // stored picture (px)

/** Picks a profile picture: a photo (camera or file, cropped and zoomed here) or one of the
 *  gallery pictures. Nothing is uploaded until the form is saved. */
export default function AvatarEditor({
  name,
  color,
  current,
  onChange,
}: {
  name: string
  color: string
  current: string | null
  onChange: (change: AvatarChange | null) => void
}) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState<string | null>(current)
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [gallery, setGallery] = useState<string[] | null>(null)
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)
  const camera = useRef<HTMLInputElement>(null)
  const file = useRef<HTMLInputElement>(null)

  // the image covers the crop window at zoom 1
  const base = image ? VIEW / Math.min(image.naturalWidth, image.naturalHeight) : 1
  const scale = base * zoom
  const clamp = (o: { x: number; y: number }, s = scale) => {
    if (!image) return o
    const maxX = Math.max(0, (image.naturalWidth * s - VIEW) / 2)
    const maxY = Math.max(0, (image.naturalHeight * s - VIEW) / 2)
    return { x: Math.min(maxX, Math.max(-maxX, o.x)), y: Math.min(maxY, Math.max(-maxY, o.y)) }
  }

  const load = (f: File | undefined) => {
    if (!f) return
    const url = URL.createObjectURL(f)
    const img = new Image()
    img.onload = () => {
      setImage(img)
      setZoom(1)
      setOffset({ x: 0, y: 0 })
    }
    img.src = url
  }

  useEffect(() => () => {
    if (image) URL.revokeObjectURL(image.src)
  }, [image])

  const apply = () => {
    if (!image) return
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = OUTPUT
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const k = OUTPUT / VIEW
    const w = image.naturalWidth * scale * k
    const h = image.naturalHeight * scale * k
    ctx.drawImage(image, OUTPUT / 2 - w / 2 + offset.x * k, OUTPUT / 2 - h / 2 + offset.y * k, w, h)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        onChange({ kind: 'photo', blob })
        setPreview(URL.createObjectURL(blob))
        setImage(null)
      },
      'image/jpeg',
      0.9,
    )
  }

  const pickGallery = (entry: string) => {
    onChange({ kind: 'gallery', name: entry })
    setPreview(`/avatars/${entry}.webp`)
    setGallery(null)
  }

  return (
    <div className={styles.editor}>
      <div className={styles.row}>
        <Avatar name={name || '?'} color={color} avatar={preview} size={72} />
        <div className={styles.buttons}>
          <button type="button" className="button" onClick={() => camera.current?.click()}>
            📷 {t('avatar.takePhoto')}
          </button>
          <button type="button" className="button" onClick={() => file.current?.click()}>
            {t('avatar.choosePhoto')}
          </button>
          <button
            type="button"
            className="button"
            onClick={() =>
              gallery ? setGallery(null) : void getJson<string[]>('/api/players/avatars/gallery').then(setGallery)
            }
          >
            {t('avatar.gallery')}
          </button>
          {preview && (
            <button
              type="button"
              className="button danger"
              onClick={() => {
                onChange({ kind: 'remove' })
                setPreview(null)
              }}
            >
              {t('avatar.remove')}
            </button>
          )}
        </div>
        {/* capture opens the front camera on phones; the second input picks an existing file */}
        <input ref={camera} type="file" accept="image/*" capture="user" hidden onChange={(e) => load(e.target.files?.[0])} />
        <input ref={file} type="file" accept="image/*" hidden onChange={(e) => load(e.target.files?.[0])} />
      </div>

      {gallery && (
        <div className={styles.gallery}>
          {gallery.map((entry) => (
            <button key={entry} type="button" className={styles.galleryItem} onClick={() => pickGallery(entry)} aria-label={entry}>
              <img src={`/avatars/${entry}.webp`} alt="" />
            </button>
          ))}
        </div>
      )}

      {image && (
        <div className={styles.crop}>
          <div
            className={styles.window}
            style={{ width: VIEW, height: VIEW }}
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId)
              drag.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y }
            }}
            onPointerMove={(e) => {
              const d = drag.current
              if (d) setOffset(clamp({ x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y }))
            }}
            onPointerUp={() => (drag.current = null)}
          >
            <img
              src={image.src}
              alt=""
              draggable={false}
              style={{
                width: image.naturalWidth * scale,
                height: image.naturalHeight * scale,
                transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))`,
              }}
            />
          </div>
          <label className={styles.zoom}>
            {t('avatar.zoom')}
            <input
              type="range"
              min={1}
              max={4}
              step={0.01}
              value={zoom}
              onChange={(e) => {
                const z = Number(e.target.value)
                setZoom(z)
                setOffset((o) => clamp(o, base * z))
              }}
            />
          </label>
          <p className="muted">{t('avatar.cropHint')}</p>
          <div className={styles.buttons}>
            <button type="button" className="button" onClick={() => setImage(null)}>
              {t('common.cancel')}
            </button>
            <button type="button" className="button primary" onClick={apply}>
              {t('avatar.use')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
