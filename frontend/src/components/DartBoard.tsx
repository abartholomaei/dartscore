import { useMemo } from 'react'
import { R, SEGMENT_DEG, SEGMENTS, dartCenter, scoreAt } from '../dart'
import styles from './DartBoard.module.css'

type Props = {
  /** darts to mark on the board (labels); drawn at the middle of their field */
  darts?: string[]
  /** highlighted dart (e.g. selected for correction) */
  selected?: number | null
  /** tap on the board -> dart label; omit for a display-only board */
  onSelect?: (label: string) => void
  disabled?: boolean
}

const RINGS: [number, number, 'single' | 'double' | 'triple'][] = [
  [R.doubleInner, R.doubleOuter, 'double'],
  [R.tripleOuter, R.doubleInner, 'single'],
  [R.tripleInner, R.tripleOuter, 'triple'],
  [R.outerBull, R.tripleInner, 'single'],
]

function arc(rIn: number, rOut: number, fromDeg: number, toDeg: number): string {
  // SVG y points down: board (x, y) -> (x, -y)
  const p = (r: number, d: number) => {
    const a = (d * Math.PI) / 180
    return `${(r * Math.cos(a)).toFixed(2)} ${(-r * Math.sin(a)).toFixed(2)}`
  }
  return `M ${p(rOut, fromDeg)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, toDeg)} L ${p(rIn, toDeg)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, fromDeg)} Z`
}

/** Top-down dartboard: input by tapping, display of the current turn's darts. */
export default function DartBoard({ darts = [], selected = null, onSelect, disabled }: Props) {
  const fields = useMemo(
    () =>
      SEGMENTS.flatMap((number, i) => {
        const center = 90 - i * SEGMENT_DEG
        const dark = i % 2 === 0
        return RINGS.map(([rIn, rOut, ring]) => ({
          key: `${number}-${ring}-${rIn}`,
          d: arc(rIn, rOut, center + SEGMENT_DEG / 2, center - SEGMENT_DEG / 2),
          className:
            ring === 'single' ? (dark ? styles.dark : styles.light) : dark ? styles.red : styles.green,
        }))
      }),
    [],
  )

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!onSelect || disabled) return
    const rect = e.currentTarget.getBoundingClientRect()
    const size = 2 * R.board
    const x = ((e.clientX - rect.left) / rect.width) * size - R.board
    const y = R.board - ((e.clientY - rect.top) / rect.height) * size
    onSelect(scoreAt(x, y))
  }

  return (
    <svg
      className={`${styles.board} ${onSelect && !disabled ? styles.interactive : ''}`}
      viewBox={`${-R.board} ${-R.board} ${2 * R.board} ${2 * R.board}`}
      onPointerDown={onPointerDown}
      role={onSelect ? 'button' : 'img'}
      aria-label="Dartboard"
    >
      <circle r={R.board} className={styles.surround} />
      {fields.map((f) => (
        <path key={f.key} d={f.d} className={f.className} />
      ))}
      <circle r={R.outerBull} className={styles.green} />
      <circle r={R.bull} className={styles.red} />
      {SEGMENTS.map((number, i) => {
        const a = ((90 - i * SEGMENT_DEG) * Math.PI) / 180
        const r = (R.doubleOuter + R.board) / 2
        return (
          <text
            key={number}
            x={r * Math.cos(a)}
            y={-r * Math.sin(a)}
            className={styles.number}
            dominantBaseline="central"
            textAnchor="middle"
          >
            {number}
          </text>
        )
      })}
      {darts.map((label, i) => {
        const pos = dartCenter(label)
        if (!pos) return null
        return (
          <g key={i} className={i === selected ? styles.hitSelected : styles.hit}>
            <circle cx={pos[0]} cy={-pos[1]} r={9} />
            <text x={pos[0]} y={-pos[1]} dominantBaseline="central" textAnchor="middle">
              {i + 1}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
