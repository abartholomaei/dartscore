// Board geometry and dart labels, mirroring dartscore.vision.board / dartscore.game.dart.

export const SEGMENTS = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
export const SEGMENT_DEG = 18
export const R = {
  bull: 6.35,
  outerBull: 15.9,
  tripleInner: 99,
  tripleOuter: 107,
  doubleInner: 162,
  doubleOuter: 170,
  board: 225,
}

export type Multiplier = 1 | 2 | 3

/** 'T20', 'D16', 'S5', '25', 'BULL', 'MISS' */
export function dartLabel(segment: number, multiplier: number): string {
  if (segment === 0) return 'MISS'
  if (segment === 25) return multiplier === 2 ? 'BULL' : '25'
  return `${'SDT'[multiplier - 1]}${segment}`
}

export function parseDart(label: string): { segment: number; multiplier: number } {
  if (label === 'MISS') return { segment: 0, multiplier: 0 }
  if (label === 'BULL') return { segment: 25, multiplier: 2 }
  if (label === '25') return { segment: 25, multiplier: 1 }
  return { segment: Number(label.slice(1)), multiplier: 'SDT'.indexOf(label[0]) + 1 }
}

export function dartPoints(label: string): number {
  const { segment, multiplier } = parseDart(label)
  return segment * multiplier
}

/** Board angle (degrees, 0 = right, counterclockwise) of a segment's center. */
function segmentAngle(segment: number): number {
  return 90 - SEGMENTS.indexOf(segment) * SEGMENT_DEG
}

/** Where to draw a dart that has no measured position: the middle of its field (mm). */
export function dartCenter(label: string): [number, number] | null {
  const { segment, multiplier } = parseDart(label)
  if (segment === 0) return null
  if (segment === 25) return multiplier === 2 ? [0, 0] : [0, (R.bull + R.outerBull) / 2]
  const r =
    multiplier === 3
      ? (R.tripleInner + R.tripleOuter) / 2
      : multiplier === 2
        ? (R.doubleInner + R.doubleOuter) / 2
        : (R.outerBull + R.tripleInner) / 2
  const a = (segmentAngle(segment) * Math.PI) / 180
  return [r * Math.cos(a), r * Math.sin(a)]
}

/** Which field is at this board position (mm, y up)? */
export function scoreAt(x: number, y: number): string {
  const r = Math.hypot(x, y)
  if (r <= R.bull) return 'BULL'
  if (r <= R.outerBull) return '25'
  if (r > R.doubleOuter) return 'MISS'
  const angle = (Math.atan2(y, x) * 180) / Math.PI
  const fromTop = (((90 - angle + SEGMENT_DEG / 2) % 360) + 360) % 360
  const segment = SEGMENTS[Math.floor(fromTop / SEGMENT_DEG) % 20]
  if (r > R.tripleInner && r <= R.tripleOuter) return dartLabel(segment, 3)
  if (r > R.doubleInner) return dartLabel(segment, 2)
  return dartLabel(segment, 1)
}
