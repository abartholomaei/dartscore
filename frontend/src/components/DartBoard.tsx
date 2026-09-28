import { useMemo } from 'react'
import { R, SEGMENT_DEG, SEGMENTS, dartCenter, parseDart, scoreAt } from '../dart'
import styles from './DartBoard.module.css'

type Props = {
  /** darts to mark on the board (labels); drawn at the middle of their field */
  darts?: string[]
  /** measured positions (mm) drawn as small dots, e.g. a heatmap of many darts */
  points?: [number, number][]
  /** measured positions (mm) of `darts`; missing ones are drawn at the middle of their field */
  positions?: ([number, number] | null)[]
  /** fields to aim at, highlighted: 'T20', 'D16', 'S5', '20' (whole number), 'D'/'T' (any
   *  double/triple), '25', 'BULL' */
  targets?: string[]
  /** the first target is the next one (checkout route): drawn stronger (default) */
  emphasizeFirst?: boolean
  /** fields that no longer count (e.g. closed cricket numbers), drawn faded */
  dimmed?: string[]
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

/** SVG shapes covering a target label (see Props.targets). */
function targetShapes(label: string): { d?: string; ring?: [number, number] }[] {
  if (label === 'D') return [{ ring: [R.doubleInner, R.doubleOuter] }]
  if (label === 'T') return [{ ring: [R.tripleInner, R.tripleOuter] }]
  if (label === 'BULL') return [{ ring: [0, R.bull] }]
  if (label === '25') return [{ ring: [R.bull, R.outerBull] }]
  const whole = /^\d+$/.test(label)
  const { segment, multiplier } = whole ? { segment: Number(label), multiplier: 0 } : parseDart(label)
  if (segment === 25) return [{ ring: [0, R.outerBull] }]
  const i = SEGMENTS.indexOf(segment)
  if (i < 0) return []
  const center = 90 - i * SEGMENT_DEG
  const wedge = (rIn: number, rOut: number) => ({ d: arc(rIn, rOut, center + SEGMENT_DEG / 2, center - SEGMENT_DEG / 2) })
  if (multiplier === 0) return [wedge(R.outerBull, R.doubleOuter)]
  if (multiplier === 3) return [wedge(R.tripleInner, R.tripleOuter)]
  if (multiplier === 2) return [wedge(R.doubleInner, R.doubleOuter)]
  return [wedge(R.outerBull, R.tripleInner), wedge(R.tripleOuter, R.doubleInner)]
}

function Shapes({ label, className }: { label: string; className: string }) {
  return targetShapes(label).map((shape, i) =>
    shape.d ? (
      <path key={i} d={shape.d} className={className} />
    ) : shape.ring && shape.ring[0] === 0 ? (
      <circle key={i} r={shape.ring[1]} className={className} />
    ) : shape.ring ? (
      <circle
        key={i}
        r={(shape.ring[0] + shape.ring[1]) / 2}
        className={className}
        style={{ fill: 'none', strokeWidth: shape.ring[1] - shape.ring[0] }}
      />
    ) : null,
  )
}

function arc(rIn: number, rOut: number, fromDeg: number, toDeg: number): string {
  // SVG y points down: board (x, y) -> (x, -y)
  const p = (r: number, d: number) => {
    const a = (d * Math.PI) / 180
    return `${(r * Math.cos(a)).toFixed(2)} ${(-r * Math.sin(a)).toFixed(2)}`
  }
  return `M ${p(rOut, fromDeg)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, toDeg)} L ${p(rIn, toDeg)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, fromDeg)} Z`
}

/** Top-down dartboard: input by tapping, display of the current turn's darts. */
export default function DartBoard({
  darts = [],
  positions = [],
  points = [],
  targets = [],
  dimmed = [],
  emphasizeFirst = true,
  selected = null,
  onSelect,
  disabled,
}: Props) {
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
      {dimmed.length > 0 && (
        <g className={styles.dimmed}>
          {dimmed.map((label) => (
            <Shapes key={label} label={label} className={styles.dim} />
          ))}
        </g>
      )}
      {targets.length > 0 && (
        <g className={styles.targets}>
          {targets.map((label, i) => (
            <Shapes key={`${label}-${i}`} label={label} className={i === 0 && emphasizeFirst ? styles.targetFirst : styles.target} />
          ))}
        </g>
      )}
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
      {points.length > 0 && (
        <g className={styles.points}>
          {points.map(([x, y], i) => (
            <circle key={i} cx={x} cy={-y} r={5} />
          ))}
        </g>
      )}
      {darts.map((label, i) => {
        // typed darts have no position: spread repeated fields a little so each stays visible
        const center = dartCenter(label)
        const pos = positions[i] ?? (center && [center[0] + (i - 1) * 6, center[1] + (i % 2) * 4])
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
