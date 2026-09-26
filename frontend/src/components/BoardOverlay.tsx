import type { Overlay } from '../api'
import styles from './BoardOverlay.module.css'

type Props = {
  overlay: Overlay
  /** natural image size the overlay coordinates refer to */
  width: number
  height: number
  showLabels?: boolean
  children?: React.ReactNode
}

/** Board wires projected into a camera image, drawn on top of the image (same size box). */
export default function BoardOverlay({ overlay, width, height, showLabels = true, children }: Props) {
  const fontSize = width / 55
  return (
    <svg className={styles.svg} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <g className={styles.wires}>
        {overlay.rings.map((ring, i) => (
          <polyline key={i} points={ring.map(([x, y]) => `${x},${y}`).join(' ')} />
        ))}
        {overlay.wires.map(([[x1, y1], [x2, y2]], i) => (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />
        ))}
      </g>
      {showLabels && (
        <g className={styles.labels} fontSize={fontSize}>
          {overlay.labels.map(([number, [x, y]]) => (
            <text key={number} x={x} y={y} dominantBaseline="central" textAnchor="middle">
              {number}
            </text>
          ))}
        </g>
      )}
      {children}
    </svg>
  )
}
