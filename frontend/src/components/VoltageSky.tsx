import { useEffect, useRef } from 'react'
import styles from './VoltageStage.module.css'

/** What just happened on the board: a dart landed, a ton+ visit, a 180 or a bust. */
export type Strike = { key: number; kind: 'dart' | 'ton' | 'storm' | 'bust'; player?: number }

type Point = [number, number]
type Bolt = { paths: Point[][]; life: number; decay: number; color: string; width: number; front: boolean }
type Spark = { x: number; y: number; vx: number; vy: number; life: number; decay: number; color: string }
type Ember = { x: number; y: number; vy: number; phase: number; drift: number; size: number; sprite: number; alpha: number }

const EMBER_COLORS = ['56 189 248', '167 139 250', '253 224 71']

/** Jagged line from a to b by midpoint displacement, with a few side branches. */
function lightning(a: Point, b: Point, spread: number, branches: boolean): Point[][] {
  let points: Point[] = [a, b]
  let offset = Math.hypot(b[0] - a[0], b[1] - a[1]) * spread
  for (let level = 0; level < 6; level++) {
    const next: Point[] = [points[0]]
    for (let i = 1; i < points.length; i++) {
      const [x1, y1] = points[i - 1]
      const [x2, y2] = points[i]
      const len = Math.hypot(x2 - x1, y2 - y1) || 1
      const d = (Math.random() - 0.5) * offset
      next.push([(x1 + x2) / 2 + (-(y2 - y1) / len) * d, (y1 + y2) / 2 + ((x2 - x1) / len) * d], points[i])
    }
    points = next
    offset /= 2
  }
  const paths = [points]
  if (branches) {
    for (let i = 8; i < points.length - 8; i += 6) {
      if (Math.random() > 0.22) continue
      const [x, y] = points[i]
      const dir = Math.atan2(b[1] - a[1], b[0] - a[0]) + (Math.random() - 0.5) * 1.6
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]) * (0.12 + Math.random() * 0.22)
      paths.push(...lightning([x, y], [x + Math.cos(dir) * len, y + Math.sin(dir) * len], 0.3, false))
    }
  }
  return paths
}

function glowSprite(rgb: string): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = c.height = 32
  const g = c.getContext('2d')!
  const grad = g.createRadialGradient(16, 16, 0, 16, 16, 16)
  grad.addColorStop(0, 'rgb(255 255 255 / 1)')
  grad.addColorStop(0.25, `rgb(${rgb} / 0.9)`)
  grad.addColorStop(1, `rgb(${rgb} / 0)`)
  g.fillStyle = grad
  g.fillRect(0, 0, 32, 32)
  return c
}

/** Animated backdrop of the Voltage stage: rising embers and distant lightning behind the
 *  board, strikes, sparks and crackling arcs on the active battery in front of it. Targets
 *  are found in the stage's DOM (`data-volt` attributes). */
export default function VoltageSky({ strike }: { strike: Strike | null }) {
  const back = useRef<HTMLCanvasElement>(null)
  const front = useRef<HTMLCanvasElement>(null)
  const fire = useRef<((s: Strike) => void) | null>(null)

  useEffect(() => {
    const bc = back.current
    const fc = front.current
    const b = bc?.getContext('2d')
    const f = fc?.getContext('2d')
    if (!bc || !fc || !b || !f) return
    const stage = bc.parentElement!
    const sprites = EMBER_COLORS.map(glowSprite)
    const bolts: Bolt[] = []
    const sparks: Spark[] = []
    let embers: Ember[] = []
    let w = 0
    let h = 0
    let flash = 0

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
      w = stage.clientWidth
      h = stage.clientHeight
      for (const [c, ctx] of [[bc, b], [fc, f]] as const) {
        c.width = w * dpr
        c.height = h * dpr
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      }
      const count = Math.min(180, Math.round((w * h) / 9000))
      embers = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vy: 0.2 + Math.random() * 0.9,
        phase: Math.random() * Math.PI * 2,
        drift: 0.3 + Math.random() * 1.2,
        size: 3 + Math.random() * 9,
        sprite: Math.floor(Math.random() * sprites.length),
        alpha: 0.25 + Math.random() * 0.6,
      }))
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(stage)

    // screen position of an element in the stage (center, or a random point on its border)
    const locate = (selector: string, edge = false): Point | null => {
      const el = stage.querySelectorAll(selector)
      const target = el[el.length - 1]
      if (!target) return null
      const r = target.getBoundingClientRect()
      const s = stage.getBoundingClientRect()
      if (!edge) return [r.left - s.left + r.width / 2, r.top - s.top + r.height / 2]
      const t = Math.random() * 2 * (r.width + r.height)
      const x = t < r.width ? t : t < r.width + r.height ? r.width : t < 2 * r.width + r.height ? 2 * r.width + r.height - t : 0
      const y = t < r.width ? 0 : t < r.width + r.height ? t - r.width : t < 2 * r.width + r.height ? r.height : 2 * (r.width + r.height) - t
      return [r.left - s.left + x, r.top - s.top + y]
    }

    const bolt = (from: Point, to: Point, opts: Partial<Bolt> & { spread?: number; branches?: boolean } = {}) => {
      bolts.push({
        paths: lightning(from, to, opts.spread ?? 0.22, opts.branches ?? true),
        life: 1,
        decay: opts.decay ?? 0.045,
        color: opts.color ?? '125 211 252',
        width: opts.width ?? 1,
        front: opts.front ?? true,
      })
    }

    const burst = (at: Point, n: number, colors: string[], speed = 6, up = false) => {
      for (let i = 0; i < n; i++) {
        const a = up ? -Math.PI / 2 + (Math.random() - 0.5) * 2.4 : Math.random() * Math.PI * 2
        const v = speed * (0.3 + Math.random())
        sparks.push({
          x: at[0], y: at[1], vx: Math.cos(a) * v, vy: Math.sin(a) * v,
          life: 1, decay: 0.012 + Math.random() * 0.025, color: colors[Math.floor(Math.random() * colors.length)],
        })
      }
    }

    const sky = (): Point => [Math.random() * w, -10]
    const timers: number[] = []
    const later = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms))

    fire.current = (s) => {
      const cell = `[data-volt-player="${s.player}"]`
      if (s.kind === 'dart') {
        const at = locate('[data-volt="dart"]')
        if (!at) return
        bolt([at[0] + (Math.random() - 0.5) * w * 0.4, -10], at, { width: 1.4, decay: 0.05 })
        burst(at, 40, ['253 224 71', '255 255 255', '125 211 252'], 5)
        flash = Math.max(flash, 0.35)
      } else if (s.kind === 'ton' || s.kind === 'storm') {
        const n = s.kind === 'storm' ? 16 : 5
        for (let i = 0; i < n; i++) {
          later(i * (s.kind === 'storm' ? 110 : 140), () => {
            const at = locate(cell, true) ?? [w / 2, h / 2]
            bolt(sky(), at, { width: s.kind === 'storm' ? 2 : 1.5, decay: 0.035 })
            burst(at, 18, ['253 224 71', '255 255 255'], 5)
            flash = Math.max(flash, s.kind === 'storm' ? 0.9 : 0.55)
          })
        }
        if (s.kind === 'storm') {
          for (let i = 0; i < 10; i++) later(200 + i * 150, () => bolt(sky(), [Math.random() * w, h * (0.4 + Math.random() * 0.6)], { front: false, width: 1.6 }))
        }
      } else {
        // bust: the battery shorts out - red sparks and sputtering arcs
        const at = locate(cell)
        if (!at) return
        burst(at, 70, ['248 113 113', '251 146 60', '255 255 255'], 4, true)
        for (let i = 0; i < 6; i++) {
          later(i * 90, () => {
            const p = locate(cell, true)
            const q = locate(cell, true)
            if (p && q) bolt(p, q, { color: '248 113 113', spread: 0.5, branches: false, decay: 0.08 })
          })
        }
      }
    }

    let last = performance.now()
    let nextAmbient = last + 1200
    let nextCrackle = last + 400
    let frame = 0

    const drawBolts = (ctx: CanvasRenderingContext2D, isFront: boolean) => {
      for (const bo of bolts) {
        if (bo.front !== isFront) continue
        const a = bo.life * (0.55 + Math.random() * 0.45)
        for (const [i, path] of bo.paths.entries()) {
          const thin = i === 0 ? 1 : 0.55
          ctx.beginPath()
          ctx.moveTo(path[0][0], path[0][1])
          for (let k = 1; k < path.length; k++) ctx.lineTo(path[k][0], path[k][1])
          ctx.strokeStyle = `rgb(${bo.color} / ${0.14 * a})`
          ctx.lineWidth = 12 * bo.width * thin
          ctx.stroke()
          ctx.strokeStyle = `rgb(${bo.color} / ${0.5 * a})`
          ctx.lineWidth = 4 * bo.width * thin
          ctx.stroke()
          ctx.strokeStyle = `rgb(255 255 255 / ${a})`
          ctx.lineWidth = 1.4 * bo.width * thin
          ctx.stroke()
        }
      }
    }

    const tick = (now: number) => {
      const dt = Math.min(3, (now - last) / 16.7)
      last = now

      // distant lightning somewhere in the sky
      if (now > nextAmbient) {
        const from: Point = [Math.random() * w, -10]
        const to: Point = [from[0] + (Math.random() - 0.5) * w * 0.5, h * (0.25 + Math.random() * 0.5)]
        bolt(from, to, { front: false, width: 0.9 + Math.random() * 0.8, decay: 0.04 })
        if (Math.random() < 0.35) later(90, () => bolt(from, [to[0] + 40, to[1] * 0.8], { front: false, width: 0.7 }))
        flash = Math.max(flash, 0.3 + Math.random() * 0.3)
        nextAmbient = now + 1500 + Math.random() * 3500
      }
      // crackling arcs along the active battery
      if (now > nextCrackle) {
        const p = locate('[data-volt="active"]', true)
        const q = p && locate('[data-volt="active"]', true)
        if (p && q && Math.hypot(p[0] - q[0], p[1] - q[1]) < 160) {
          bolt(p, q, { spread: 0.45, branches: false, decay: 0.11, width: 0.8 })
          if (Math.random() < 0.5) burst(p, 5, ['125 211 252', '255 255 255'], 2.5)
        }
        nextCrackle = now + 120 + Math.random() * 380
      }

      // back layer: flash, embers, distant bolts
      b.globalCompositeOperation = 'source-over'
      b.clearRect(0, 0, w, h)
      if (flash > 0.01) {
        b.fillStyle = `rgb(186 230 253 / ${flash * 0.22})`
        b.fillRect(0, 0, w, h)
        flash *= Math.pow(0.86, dt)
      }
      b.globalCompositeOperation = 'lighter'
      for (const e of embers) {
        e.y -= e.vy * dt * (1 + flash * 3)
        e.phase += 0.02 * dt
        e.x += Math.sin(e.phase) * e.drift * 0.3 * dt
        if (e.y < -20) {
          e.y = h + 20
          e.x = Math.random() * w
        }
        b.globalAlpha = e.alpha * (0.7 + 0.3 * Math.sin(e.phase * 3))
        b.drawImage(sprites[e.sprite], e.x - e.size / 2, e.y - e.size / 2, e.size, e.size)
      }
      b.globalAlpha = 1
      drawBolts(b, false)

      // front layer: strikes, arcs, sparks
      f.clearRect(0, 0, w, h)
      f.globalCompositeOperation = 'lighter'
      f.lineCap = 'round'
      f.lineJoin = 'round'
      drawBolts(f, true)
      for (const s of sparks) {
        s.vy += 0.12 * dt
        s.vx *= Math.pow(0.97, dt)
        s.x += s.vx * dt
        s.y += s.vy * dt
        s.life -= s.decay * dt
        f.strokeStyle = `rgb(${s.color} / ${Math.max(0, s.life)})`
        f.lineWidth = 2
        f.beginPath()
        f.moveTo(s.x, s.y)
        f.lineTo(s.x - s.vx * 2.2, s.y - s.vy * 2.2)
        f.stroke()
      }
      for (let i = bolts.length - 1; i >= 0; i--) {
        bolts[i].life -= bolts[i].decay * dt
        if (bolts[i].life <= 0) bolts.splice(i, 1)
      }
      for (let i = sparks.length - 1; i >= 0; i--) if (sparks[i].life <= 0) sparks.splice(i, 1)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      timers.forEach((t) => window.clearTimeout(t))
      fire.current = null
    }
  }, [])

  useEffect(() => {
    if (strike) fire.current?.(strike)
  }, [strike])

  return (
    <>
      <canvas ref={back} className={styles.skyBack} aria-hidden />
      <canvas ref={front} className={styles.skyFront} aria-hidden />
    </>
  )
}
