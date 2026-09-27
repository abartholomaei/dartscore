import QRCode from 'qrcode'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getJson } from '../api'
import styles from './ConnectQr.module.css'

/** QR code with the address of dartscore in the home network, to open it on a phone. */
export default function ConnectQr({ size = 180 }: { size?: number }) {
  const { t } = useTranslation()
  const [urls, setUrls] = useState<string[]>([])
  const [index, setIndex] = useState(0)
  const [image, setImage] = useState<string | null>(null)

  useEffect(() => {
    getJson<{ urls: string[] }>('/api/network')
      .then((r) => setUrls(r.urls))
      .catch(() => undefined)
  }, [])

  const url = urls[index]
  useEffect(() => {
    if (!url) return
    void QRCode.toDataURL(url, { width: size * 2, margin: 1, color: { dark: '#0b0b0c', light: '#ffffff' } }).then(setImage)
  }, [url, size])

  if (!url) return null
  return (
    <div className={styles.qr}>
      {image && <img src={image} width={size} height={size} alt={t('connect.qrAlt', { url })} />}
      <div className={styles.text}>
        <strong>{t('connect.title')}</strong>
        <span className="muted">{t('connect.hint')}</span>
        <code>{url}</code>
        {urls.length > 1 && (
          <button className="button" onClick={() => setIndex((i) => (i + 1) % urls.length)}>
            {t('connect.otherAddress')}
          </button>
        )}
      </div>
    </div>
  )
}
