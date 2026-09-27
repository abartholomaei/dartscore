import { useEffect, useRef } from 'react'
import styles from './Particles.module.css'

export type Effect = '180' | 'checkout' | 'bust'

type Particle = { x: number; y: number; vx: number; vy: number; size: number; color: string; spin: number; angle: number; life: number; shape: 'rect' | 'dot' }

const COLORS: Record<Effect, string[]> = {
  '180': ['#22c55e', '#84cc16', '#facc15', '#ffffff', '#16a34a'],
  checkout: ['#22c55e', '#ffffff', '#facc15', '#38bdf8', '#f472b6'],
  bust: ['#6b7280', '#9ca3af', '#4b5563'],
}

/** A short particle effect over the whole screen: confetti (180), fireworks (checkout) or a
 *  puff of dust (bust). Plain canvas, a few hundred particles, stops after ~2.5 s. */
export default function Particles({ effect }: { effect: Effect }) {
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const el = canvas.current
    const ctx = el?.getContext('2d')
    if (!el || !ctx) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = window.innerWidth
    const h = window.innerHeight
    el.width = w * dpr
    el.height = h * dpr
    ctx.scale(dpr, dpr)
    const colors = COLORS[effect]
    const pick = () => colors[Math.floor(Math.random() * colors.length)]
    const particles: Particle[] = []
    const spawn = (x: number, y: number, n: number, speed: number, shape: Particle['shape'], spread = Math.PI * 2, dir = 0) => {
      for (let i = 0; i < n; i++) {
        const a = dir + (Math.random() - 0.5) * spread
        const v = speed * (0.4 + Math.random() * 0.8)
        particles.push({
          x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v,
          size: shape === 'rect' ? 6 + Math.random() * 6 : 2 + Math.random() * 3,
          color: pick(), spin: (Math.random() - 0.5) * 0.3, angle: Math.random() * Math.PI, life: 1, shape,
        })
      }
    }
    if (effect === '180') {
      // confetti cannons from both lower corners
      spawn(0, h, 140, 16, 'rect', 0.7, -Math.PI / 3)
      spawn(w, h, 140, 16, 'rect', 0.7, (-2 * Math.PI) / 3)
    } else if (effect === 'checkout') {
      for (let i = 0; i < 4; i++) {
        window.setTimeout(() => spawn(w * (0.2 + Math.random() * 0.6), h * (0.2 + Math.random() * 0.35), 70, 7, 'dot'), i * 350)
      }
    } else {
      spawn(w / 2, h * 0.55, 60, 3.5, 'dot', Math.PI, -Math.PI / 2)
    }
    const gravity = effect === 'bust' ? 0.02 : 0.25
    const drag = effect === '180' ? 0.985 : 0.97
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      ctx.clearRect(0, 0, w, h)
      for (const p of particles) {
        p.vx *= drag
        p.vy = p.vy * drag + gravity
        p.x += p.vx
        p.y += p.vy
        p.angle += p.spin
        p.life -= effect === 'checkout' ? 0.012 : 0.007
        if (p.life <= 0) continue
        ctx.globalAlpha = Math.min(1, p.life * 1.5)
        ctx.fillStyle = p.color
        if (p.shape === 'rect') {
          ctx.save()
          ctx.translate(p.x, p.y)
          ctx.rotate(p.angle)
          ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2)
          ctx.restore()
        } else {
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
          ctx.fill()
        }
      }
      if (now - start < 2800) frame = requestAnimationFrame(tick)
      else ctx.clearRect(0, 0, w, h)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [effect])

  return <canvas ref={canvas} className={styles.canvas} aria-hidden="true" />
}
