import { useEffect, useRef, useState } from 'react'

/** Monsters as puppets: every kind is ONE still image, deformed on the GPU each frame
 *  (breathing, jelly wobble, swinging arms, flapping wings, blinking, hit and fall). Drawing
 *  every frame by AI made the motion jitter - details and size changed from frame to frame -
 *  while a deformed still stays identical and runs at the display's frame rate. */

type Limb = { pivot: [number, number]; rect: [number, number, number, number]; amp: number; speed: number; phase?: number }
type Rig = {
  eyes: [number, number, number, number][] // cx, cy, rx, ry in texture space (y down)
  skin: [number, number, number]
  breath: number // squash & stretch amount
  breathSpeed: number
  jelly?: number // sideways wobble growing with height
  sway?: number // bending around the feet
  hop?: number // little jumps (imp)
  hover?: number // floating up and down (bat), in texture units
  foot: number // texture y of the feet
  limbs: Limb[]
}

const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number]

// texture space: 0..1, x to the right, y down; measured on the 512 px stills
const RIGS: Record<string, Rig> = {
  blob: {
    eyes: [
      [0.405, 0.335, 0.078, 0.088],
      [0.578, 0.37, 0.072, 0.082],
    ],
    skin: rgb('#a8dc2c'),
    breath: 0.045,
    breathSpeed: 2.1,
    jelly: 0.04,
    sway: 0.035,
    foot: 0.96,
    limbs: [
      { pivot: [0.3, 0.5], rect: [0, 0.38, 0.3, 0.76], amp: 0.13, speed: 2.1 },
      { pivot: [0.7, 0.5], rect: [0.7, 0.38, 1, 0.76], amp: -0.13, speed: 2.1, phase: 0.9 },
      { pivot: [0.6, 0.22], rect: [0.45, 0, 0.82, 0.2], amp: 0.16, speed: 1.7, phase: 0.5 },
    ],
  },
  imp: {
    eyes: [
      [0.42, 0.378, 0.078, 0.082],
      [0.613, 0.43, 0.068, 0.072],
    ],
    skin: rgb('#a741e3'),
    breath: 0.025,
    breathSpeed: 3.2,
    sway: 0.02,
    hop: 0.035,
    foot: 0.97,
    limbs: [
      { pivot: [0.27, 0.3], rect: [0.05, 0.12, 0.27, 0.37], amp: 0.1, speed: 3.2, phase: 0.4 },
      { pivot: [0.78, 0.33], rect: [0.78, 0.25, 0.98, 0.38], amp: -0.1, speed: 3.2, phase: 0.4 },
      { pivot: [0.3, 0.55], rect: [0.02, 0.44, 0.3, 0.63], amp: 0.2, speed: 3.2, phase: 1.2 },
      { pivot: [0.68, 0.6], rect: [0.68, 0.55, 0.92, 0.73], amp: -0.16, speed: 3.2, phase: 2.2 },
      { pivot: [0.3, 0.72], rect: [0.04, 0.64, 0.3, 0.8], amp: 0.32, speed: 2.4 },
    ],
  },
  bat: {
    eyes: [
      [0.458, 0.47, 0.066, 0.07],
      [0.6, 0.52, 0.062, 0.066],
    ],
    skin: rgb('#f7a01a'),
    breath: 0.015,
    breathSpeed: 7,
    hover: 0.03,
    foot: 0.82,
    limbs: [
      { pivot: [0.36, 0.43], rect: [0, 0.1, 0.3, 0.76], amp: 0.42, speed: 7 },
      { pivot: [0.65, 0.43], rect: [0.71, 0.2, 1, 0.76], amp: -0.42, speed: 7 },
      { pivot: [0.42, 0.3], rect: [0.3, 0.1, 0.44, 0.28], amp: 0.06, speed: 3.5, phase: 1 },
      { pivot: [0.63, 0.3], rect: [0.6, 0.08, 0.74, 0.27], amp: -0.06, speed: 3.5, phase: 1 },
    ],
  },
  king: {
    eyes: [
      [0.43, 0.35, 0.072, 0.077],
      [0.592, 0.385, 0.067, 0.072],
    ],
    skin: rgb('#45b8ef'),
    breath: 0.035,
    breathSpeed: 1.6,
    sway: 0.018,
    foot: 0.97,
    limbs: [
      { pivot: [0.6, 0.26], rect: [0.3, 0, 0.96, 0.25], amp: 0.07, speed: 1.6, phase: 0.8 },
      { pivot: [0.25, 0.55], rect: [0, 0.34, 0.24, 0.58], amp: 0.14, speed: 1.6 },
      { pivot: [0.77, 0.55], rect: [0.78, 0.34, 1, 0.58], amp: -0.14, speed: 1.6, phase: 0.3 },
      { pivot: [0.2, 0.56], rect: [0, 0.6, 0.17, 0.92], amp: 0.06, speed: 1.3, phase: 1.5 },
      { pivot: [0.8, 0.56], rect: [0.83, 0.6, 1, 0.92], amp: -0.06, speed: 1.3, phase: 1.5 },
    ],
  },
}

const MAX_LIMBS = 6
const GRID = 36 // mesh cells per side
const BODY = 0.55 // texture y that sits on the monster's hit centre
const SIZE = 3.3 // sprite size as a multiple of the hit radius

const VERTEX = `
precision highp float;
attribute vec2 a_uv;
uniform vec2 u_center;   // hit centre, canvas px
uniform float u_size;    // sprite size, canvas px
uniform vec2 u_canvas;
uniform float u_time;
uniform float u_breath, u_breathSpeed, u_jelly, u_sway, u_foot;
uniform vec4 u_limbA[${MAX_LIMBS}]; // pivot.xy, amp, phase
uniform vec4 u_limbR[${MAX_LIMBS}]; // rect
uniform float u_limbSpeed[${MAX_LIMBS}];
uniform vec2 u_scale;    // squash & stretch from hits, spawn and fall (around the feet)
uniform float u_tilt;    // rotation around the feet
uniform vec2 u_offset;   // in texture units (hops, hover, knock-back)
varying vec2 v_uv;

vec2 rot(vec2 p, vec2 c, float a) {
  float s = sin(a), co = cos(a);
  p -= c;
  return c + vec2(p.x * co - p.y * s, p.x * s + p.y * co);
}

void main() {
  v_uv = a_uv;
  vec2 p = a_uv;
  for (int i = 0; i < ${MAX_LIMBS}; i++) {
    vec4 r = u_limbR[i];
    if (u_limbA[i].z == 0.0) continue;
    float w = smoothstep(r.x - 0.06, r.x + 0.02, a_uv.x) * (1.0 - smoothstep(r.z - 0.02, r.z + 0.06, a_uv.x))
            * smoothstep(r.y - 0.06, r.y + 0.02, a_uv.y) * (1.0 - smoothstep(r.w - 0.02, r.w + 0.06, a_uv.y));
    float a = u_limbA[i].z * sin(u_time * u_limbSpeed[i] + u_limbA[i].w);
    p = rot(p, u_limbA[i].xy, a * w);
  }
  float h = clamp((u_foot - p.y) / u_foot, 0.0, 1.2); // 0 at the feet, 1 at the top
  // jelly: waves travelling up the body
  p.x += u_jelly * sin(u_time * 2.3 - h * 2.6) * h * h;
  // breathing: wider and lower, then narrower and taller
  float b = sin(u_time * u_breathSpeed);
  p.x = 0.5 + (p.x - 0.5) * (1.0 + u_breath * b * (0.4 + h));
  p.y = u_foot - (u_foot - p.y) * (1.0 - u_breath * b);
  // bending around the feet
  p = rot(p, vec2(0.5, u_foot), u_sway * sin(u_time * 0.9) * h);
  // the whole body: squash, tilt, offset
  p = vec2(0.5 + (p.x - 0.5) * u_scale.x, u_foot - (u_foot - p.y) * u_scale.y);
  p = rot(p, vec2(0.5, u_foot), u_tilt);
  p += u_offset;
  vec2 px = u_center + (p - vec2(0.5, ${BODY})) * u_size;
  gl_Position = vec4(px / u_canvas * 2.0 - 1.0, 0.0, 1.0);
  gl_Position.y = -gl_Position.y;
}`

const FRAGMENT = `
precision mediump float;
uniform sampler2D u_tex;
uniform vec4 u_eye[2];
uniform float u_lid;     // 0 open .. 1 closed
uniform vec3 u_skin;
uniform float u_flash;
uniform float u_alpha;
varying vec2 v_uv;

void main() {
  vec4 c = texture2D(u_tex, v_uv);
  // eyelids come down from the top of each eye (a bit larger, so they cover its outline too);
  // the lid is the monster's own skin, taken from just above the eye
  for (int i = 0; i < 2; i++) {
    vec2 radius = u_eye[i].zw * 1.15;
    vec2 d = (v_uv - u_eye[i].xy) / radius;
    float r = dot(d, d);
    if (r < 1.0 && u_lid > 0.0) {
      float edge = mix(-1.0, 0.55, u_lid) + 0.25 * d.x * d.x; // curved lid line in eye space
      if (d.y < edge) {
        vec4 skin = texture2D(u_tex, v_uv - vec2(0.0, radius.y * 2.1));
        vec3 lid = skin.a > 0.6 ? skin.rgb / skin.a : u_skin;
        lid *= 0.9 + 0.1 * (edge - d.y);
        float line = smoothstep(edge - 0.28, edge - 0.1, d.y); // dark lashes along the edge
        float soft = smoothstep(1.0, 0.8, r); // fades into the skin at the rim
        c = vec4(mix(c.rgb / max(c.a, 0.001), mix(lid, vec3(0.06, 0.03, 0.07), line), soft) * c.a, c.a);
      }
    }
  }
  c.rgb = mix(c.rgb, vec3(c.a), u_flash);
  gl_FragColor = c * u_alpha;
}`

export type PuppetMonster = { key: string; kind: string; x: number; y: number; radius: number; dying: boolean }
export type PuppetShot = { key: number; target: string | null; kind: 'hit' | 'kill' | 'miss' | 'headshot'; fromX: number }

type State = {
  x: number
  y: number
  r: number
  born: number
  hitAt: number
  hitDir: number
  diedAt: number
  nextBlink: number
  seed: number
}

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!
  gl.shaderSource(s, src)
  gl.compileShader(s)
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader')
  return s
}

const easeOutBack = (t: number) => 1 + 2.7 * (t - 1) ** 3 + 1.7 * (t - 1) ** 2

/** A WebGL canvas over the board (same square as the SVG viewBox ±view mm). */
export default function MonsterPuppets({ monsters, shot, view }: { monsters: PuppetMonster[]; shot: PuppetShot | null; view: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const live = useRef(monsters)
  useEffect(() => {
    live.current = monsters
  }, [monsters])
  const states = useRef(new Map<string, State>())
  const handled = useRef<number | null>(null)
  const [failed, setFailed] = useState(false)

  // react to a dart: flinch, fall
  useEffect(() => {
    if (!shot || handled.current === shot.key || !shot.target) return
    handled.current = shot.key
    const s = states.current.get(shot.target)
    if (!s) return
    const now = performance.now() / 1000
    if (shot.kind === 'kill' || shot.kind === 'headshot') s.diedAt = now
    else if (shot.kind === 'hit') {
      s.hitAt = now
      s.hitDir = shot.fromX < s.x ? 1 : -1
    } else s.hitAt = now - 10 // a miss: nothing to flinch about
  }, [shot])

  useEffect(() => {
    const el = canvas.current
    if (!el) return
    const gl = el.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: true })
    if (!gl || gl.isContextLost()) {
      queueMicrotask(() => setFailed(true))
      return
    }
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const program = gl.createProgram()!
    try {
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX))
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT))
    } catch (error) {
      console.error('monster puppets:', error)
      queueMicrotask(() => setFailed(true))
      return
    }
    gl.linkProgram(program)
    gl.useProgram(program)
    const loc = (n: string) => gl.getUniformLocation(program, n)

    // the grid mesh, shared by every monster
    const uv: number[] = []
    for (let j = 0; j <= GRID; j++) for (let i = 0; i <= GRID; i++) uv.push(i / GRID, j / GRID)
    const idx: number[] = []
    for (let j = 0; j < GRID; j++)
      for (let i = 0; i < GRID; i++) {
        const a = j * (GRID + 1) + i
        idx.push(a, a + 1, a + GRID + 1, a + 1, a + GRID + 2, a + GRID + 1)
      }
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(uv), gl.STATIC_DRAW)
    const aUv = gl.getAttribLocation(program, 'a_uv')
    gl.enableVertexAttribArray(aUv)
    gl.vertexAttribPointer(aUv, 2, gl.FLOAT, false, 0, 0)
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(idx), gl.STATIC_DRAW)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)

    const textures = new Map<string, WebGLTexture>()
    for (const kind of Object.keys(RIGS)) {
      const img = new Image()
      img.onload = () => {
        const tex = gl.createTexture()!
        gl.bindTexture(gl.TEXTURE_2D, tex)
        gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img)
        gl.generateMipmap(gl.TEXTURE_2D)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
        textures.set(kind, tex)
      }
      img.src = `/arcade/monsters/${kind}.webp`
    }

    const u = {
      center: loc('u_center'), size: loc('u_size'), canvas: loc('u_canvas'), time: loc('u_time'),
      breath: loc('u_breath'), breathSpeed: loc('u_breathSpeed'), jelly: loc('u_jelly'), sway: loc('u_sway'), foot: loc('u_foot'),
      limbA: loc('u_limbA'), limbR: loc('u_limbR'), limbSpeed: loc('u_limbSpeed'),
      scale: loc('u_scale'), tilt: loc('u_tilt'), offset: loc('u_offset'),
      eye: loc('u_eye'), lid: loc('u_lid'), skin: loc('u_skin'), flash: loc('u_flash'), alpha: loc('u_alpha'),
    } // fmt: skip

    let frame = 0
    let last = performance.now() / 1000
    const render = (now: number) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
      const w = Math.round(el.clientWidth * dpr)
      const h = Math.round(el.clientHeight * dpr)
      if (el.width !== w || el.height !== h) {
        el.width = w
        el.height = h
      }
      gl.viewport(0, 0, w, h)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.uniform2f(u.canvas, w, h)
      const dt = Math.min(0.1, Math.max(0, now - last))
      last = now
      const mm = w / (2 * view)
      const seen = new Set<string>()
      for (const m of live.current) {
        seen.add(m.key)
        const rig = RIGS[m.kind]
        const tex = textures.get(m.kind)
        let s = states.current.get(m.key)
        if (!s) {
          s = { x: m.x, y: m.y, r: m.radius, born: now, hitAt: -99, hitDir: 1, diedAt: m.dying ? now : -1, nextBlink: now + 1 + Math.random() * 3, seed: Math.random() * 10 }
          states.current.set(m.key, s)
        }
        if (m.dying && s.diedAt < 0) s.diedAt = now
        // walkers stride, growing monsters swell - both eased, frame-rate independent
        const k = 1 - Math.exp(-3.2 * dt)
        s.x += (m.x - s.x) * k
        s.y += (m.y - s.y) * k
        s.r += (m.radius - s.r) * k
        if (!rig || !tex) continue

        const t = now + s.seed
        let sx = 1
        let sy = 1
        let tilt = 0
        let ox = 0
        let oy = 0
        let flash = 0
        let alpha = 1
        let lid = 0

        // spawning: pops out of the ground with an overshoot
        const born = (now - s.born - 0.35) / 0.5
        if (born < 0) continue
        if (born < 1) {
          const e = easeOutBack(born)
          sx = Math.max(0.01, e * 0.9 + 0.1)
          sy = Math.max(0.01, e)
        }
        // idle extras
        if (rig.hop && !still) {
          const ph = (t * 1.6) % 1
          const air = Math.max(0, Math.sin(ph * Math.PI * 2))
          oy -= rig.hop * air
          const land = Math.max(0, -Math.sin(ph * Math.PI * 2))
          sy *= 1 - 0.06 * land
          sx *= 1 + 0.05 * land
        }
        if (rig.hover && !still) oy -= rig.hover * (0.5 + 0.5 * Math.sin(t * rig.breathSpeed + Math.PI / 2))
        // hit: flash white, squash and knock back, then spring back
        const hit = now - s.hitAt
        if (hit < 0.7) {
          const decay = Math.exp(-hit * 7)
          flash = Math.max(flash, Math.exp(-hit * 14))
          sx *= 1 + 0.16 * decay * Math.cos(hit * 26)
          sy *= 1 - 0.16 * decay * Math.cos(hit * 26)
          tilt += s.hitDir * 0.3 * decay * Math.cos(hit * 16)
          ox += s.hitDir * 0.05 * decay
          lid = Math.max(lid, hit < 0.25 ? 1 : 0)
        }
        // falling: a startled jump, then it flattens, tips over and fades
        if (s.diedAt >= 0) {
          const d = now - s.diedAt
          flash = Math.max(flash, Math.exp(-d * 10))
          lid = 1
          if (d < 0.22) {
            const e = d / 0.22
            oy -= 0.12 * Math.sin(e * Math.PI)
            sx *= 1 - 0.12 * Math.sin(e * Math.PI)
            sy *= 1 + 0.15 * Math.sin(e * Math.PI)
          } else {
            // flattened like a pancake, with a little wobble when it lands
            const e = Math.min(1, (d - 0.22) / 0.3)
            const ease = 1 - (1 - e) ** 3
            const wobble = d > 0.52 ? 0.08 * Math.exp(-(d - 0.52) * 9) * Math.sin((d - 0.52) * 30) : 0
            sy *= 1 - 0.62 * ease + wobble
            sx *= 1 + 0.2 * ease - wobble
          }
          alpha = 1 - Math.min(1, Math.max(0, (d - 0.7) / 0.3))
          if (alpha <= 0) continue
        }
        // blinking every few seconds
        if (now > s.nextBlink) {
          const bt = now - s.nextBlink
          if (bt < 0.16) lid = Math.max(lid, Math.sin((bt / 0.16) * Math.PI))
          else s.nextBlink = now + 2 + Math.random() * 3.5
        }

        const limbA = new Float32Array(MAX_LIMBS * 4)
        const limbR = new Float32Array(MAX_LIMBS * 4)
        const limbSpeed = new Float32Array(MAX_LIMBS)
        rig.limbs.forEach((l, i) => {
          limbA.set([l.pivot[0], l.pivot[1], l.amp, l.phase ?? 0], i * 4)
          limbR.set(l.rect, i * 4)
          limbSpeed[i] = l.speed
        })
        const idle = still ? 0 : s.diedAt >= 0 ? 0.3 : 1 // a falling monster stops breathing
        gl.bindTexture(gl.TEXTURE_2D, tex)
        gl.uniform2f(u.center, (s.x + view) * mm, (view - s.y) * mm)
        gl.uniform1f(u.size, s.r * SIZE * mm)
        gl.uniform1f(u.time, t)
        gl.uniform1f(u.breath, rig.breath * idle)
        gl.uniform1f(u.breathSpeed, rig.breathSpeed)
        gl.uniform1f(u.jelly, (rig.jelly ?? 0) * idle)
        gl.uniform1f(u.sway, (rig.sway ?? 0) * idle)
        gl.uniform1f(u.foot, rig.foot)
        gl.uniform4fv(u.limbA, limbA.map((v, i) => (i % 4 === 2 ? v * idle : v)))
        gl.uniform4fv(u.limbR, limbR)
        gl.uniform1fv(u.limbSpeed, limbSpeed)
        gl.uniform2f(u.scale, sx, sy)
        gl.uniform1f(u.tilt, tilt)
        gl.uniform2f(u.offset, ox, oy)
        gl.uniform4fv(u.eye, new Float32Array(rig.eyes.flat()))
        gl.uniform1f(u.lid, lid)
        gl.uniform3fv(u.skin, rig.skin)
        gl.uniform1f(u.flash, flash * 0.85)
        gl.uniform1f(u.alpha, alpha)
        gl.drawElements(gl.TRIANGLES, idx.length, gl.UNSIGNED_SHORT, 0)
      }
      for (const key of states.current.keys()) if (!seen.has(key)) states.current.delete(key)
    }
    const draw = () => {
      frame = requestAnimationFrame(draw)
      render(performance.now() / 1000)
    }
    draw()
    // development: render any moment on demand (to inspect the motion frame by frame)
    if (import.meta.env.DEV) (window as unknown as { __puppets?: unknown }).__puppets = { render, canvas: el }
    // the canvas (and its context) is reused if the effect runs again, so only stop drawing
    return () => cancelAnimationFrame(frame)
  }, [view])

  // no WebGL: the plain stills, so the game stays playable
  if (failed)
    return (
      <svg viewBox={`${-view} ${-view} ${2 * view} ${2 * view}`} aria-hidden style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
        {monsters
          .filter((m) => !m.dying)
          .map((m) => (
            <image
              key={m.key}
              href={`/arcade/monsters/${m.kind}.webp`}
              x={m.x - (m.radius * SIZE) / 2}
              y={-m.y - m.radius * SIZE * BODY}
              width={m.radius * SIZE}
              height={m.radius * SIZE}
            />
          ))}
      </svg>
    )
  return <canvas ref={canvas} className="puppets" aria-hidden style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
}
