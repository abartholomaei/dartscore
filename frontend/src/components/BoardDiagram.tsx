import type { CalibrationCatalog } from '../api'
import styles from './BoardDiagram.module.css'

const RINGS = [6.35, 15.9, 99, 107, 162, 170]
const SEGMENT_DEG = 18

type Props = {
  catalog: CalibrationCatalog
  /** calibration point to highlight */
  activeId: string | null
  placedIds: string[]
}

/** Small top-down board that shows where the requested calibration point is. */
export default function BoardDiagram({ catalog, activeId, placedIds }: Props) {
  // board coordinates have y pointing up, SVG has y pointing down
  const polar = (r: number, deg: number): [number, number] => {
    const rad = (deg * Math.PI) / 180
    return [r * Math.cos(rad), -r * Math.sin(rad)]
  }

  return (
    <svg className={styles.svg} viewBox="-215 -215 430 430" role="img" aria-hidden="true">
      <circle r={170} className={styles.face} />
      {RINGS.map((r) => (
        <circle key={r} r={r} className={styles.wire} />
      ))}
      {catalog.segments.map((number, i) => {
        const edge = 90 - (i + 0.5) * SEGMENT_DEG
        const [x1, y1] = polar(15.9, edge)
        const [x2, y2] = polar(170, edge)
        const [tx, ty] = polar(192, 90 - i * SEGMENT_DEG)
        return (
          <g key={number}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} className={styles.wire} />
            <text x={tx} y={ty} className={styles.number} dominantBaseline="central" textAnchor="middle">
              {number}
            </text>
          </g>
        )
      })}
      {catalog.points.map((p) => {
        const active = p.id === activeId
        const placed = placedIds.includes(p.id)
        return (
          <circle
            key={p.id}
            cx={p.x_mm}
            cy={-p.y_mm}
            r={active ? 13 : 7}
            className={active ? styles.active : placed ? styles.placed : styles.open}
          />
        )
      })}
    </svg>
  )
}
