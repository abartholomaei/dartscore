import { useRef } from 'react'
import { scoreAt } from '../dart'
import styles from './ArcadeStage.module.css'

export const VIEW = 200 // mm shown around the bull (the board ends at 170)

/** Makes the board svg tappable: a tap throws a dart at that spot (mm, y up). */
export function useBoardTap(onTap: ((label: string, x: number, y: number) => void) | undefined, disabled?: boolean) {
  const ref = useRef<SVGSVGElement>(null)
  const onClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onTap || disabled || !ref.current) return
    const point = ref.current.createSVGPoint()
    point.x = e.clientX
    point.y = e.clientY
    const matrix = ref.current.getScreenCTM()
    if (!matrix) return
    const p = point.matrixTransform(matrix.inverse())
    const x = p.x
    const y = -p.y
    onTap(scoreAt(x, y), Math.round(x * 10) / 10, Math.round(y * 10) / 10)
  }
  return {
    ref,
    onClick,
    className: `${styles.board} ${onTap && !disabled ? styles.tappable : ''}`,
    viewBox: `${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`,
    role: 'img',
  }
}
