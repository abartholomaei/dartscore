import { useRef, useState } from 'react'
import MonsterPuppets, { type PuppetMonster, type PuppetShot } from '../components/MonsterPuppets'

const VIEW = 100
const KINDS = ['blob', 'imp', 'bat', 'king']

/** Development only: all monster puppets side by side, large, to judge and tune the motion. */
export default function PuppetLab() {
  const [round, setRound] = useState(0)
  const [dead, setDead] = useState<string | null>(null)
  const [shot, setShot] = useState<PuppetShot | null>(null)
  const shots = useRef(0)
  const monsters: PuppetMonster[] = KINDS.map((kind, i) => ({
    key: `${round}-${kind}`,
    kind,
    x: -75 + i * 50,
    y: 0,
    radius: 13,
    dying: dead === `${round}-${kind}`,
  }))
  const act = (kind: string, what: PuppetShot['kind']) => {
    const key = `${round}-${kind}`
    if (what === 'kill') setDead(key)
    setShot({ key: ++shots.current, target: key, kind: what, fromX: -999 })
  }
  return (
    <div style={{ display: 'grid', gap: 12, padding: 16 }}>
      <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 1', background: '#16302a', borderRadius: 16, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: '-50%', aspectRatio: 1 }}>
          <MonsterPuppets monsters={monsters} shot={shot} view={VIEW} />
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        {KINDS.map((k) => (
          <div key={k} style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
            <button className="button" onClick={() => act(k, 'hit')}>
              hit
            </button>
            <button className="button" onClick={() => act(k, 'kill')}>
              kill
            </button>
          </div>
        ))}
      </div>
      <button className="button" onClick={() => (setRound((r) => r + 1), setDead(null))}>
        respawn
      </button>
    </div>
  )
}
