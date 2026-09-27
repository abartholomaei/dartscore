import styles from './Avatar.module.css'

/** Profile picture, or the initial letter on the player's colour. */
export default function Avatar({
  name,
  color,
  avatar,
  size = 36,
}: {
  name: string
  color: string
  avatar?: string | null
  size?: number
}) {
  const style = { width: size, height: size, fontSize: size * 0.45, background: color }
  if (avatar) {
    return <img className={styles.avatar} src={avatar} alt="" style={style} draggable={false} />
  }
  return (
    <span className={styles.avatar} style={style} aria-hidden="true">
      {name.slice(0, 1).toUpperCase()}
    </span>
  )
}
