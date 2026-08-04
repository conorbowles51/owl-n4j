import { useEffect, useRef } from "react"
import { entityColours, graphCounts } from "../../data/case"
import { segment } from "../../lib/useScrollProgress"
import { PinnedSequence } from "../primitives/PinnedSequence"
import styles from "./GraphReduce.module.css"

/** Deterministic PRNG so the field is identical on every render and every machine. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * The swarm is representative of a real matter's density, not of the demo case.
 * A 121-node field does not read as a problem; thirty thousand does, and that is
 * the scale the product actually runs at. Captioned as illustrative.
 */
const SWARM = 1400
const SURVIVORS = 40

interface Node {
  x: number
  y: number
  r: number
  colour: string
  keep: boolean
  /** Resting place once the field reduces. */
  tx: number
  ty: number
}

function buildField(): Node[] {
  const rand = mulberry32(0x10a9e)
  const palette = Object.values(entityColours)
  const nodes: Node[] = []

  // Cluster centres, so the swarm reads as structure rather than noise.
  const clusters = Array.from({ length: 9 }, () => ({
    x: 0.5 + (rand() - 0.5) * 0.78,
    y: 0.5 + (rand() - 0.5) * 0.72,
  }))

  for (let i = 0; i < SWARM; i++) {
    const c = clusters[Math.floor(rand() * clusters.length)]
    const angle = rand() * Math.PI * 2
    const radius = Math.pow(rand(), 1.7) * 0.26
    const keep = i % Math.floor(SWARM / SURVIVORS) === 0 && nodes.filter((n) => n.keep).length < SURVIVORS

    // Survivors settle onto a loose ring so they are legible once the rest fades.
    const k = nodes.filter((n) => n.keep).length
    const ringAngle = (k / SURVIVORS) * Math.PI * 2
    const ringR = 0.16 + (k % 3) * 0.07

    nodes.push({
      x: c.x + Math.cos(angle) * radius,
      y: c.y + Math.sin(angle) * radius * 0.82,
      r: keep ? 3.4 + rand() * 2.2 : 1.2 + rand() * 1.6,
      colour: palette[Math.floor(rand() * palette.length)],
      keep,
      tx: 0.5 + Math.cos(ringAngle) * ringR * 1.5,
      ty: 0.5 + Math.sin(ringAngle) * ringR,
    })
  }
  return nodes
}

const FIELD = buildField()

function Field({ progress }: { progress: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const { width, height } = canvas.getBoundingClientRect()
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)

    const fade = segment(progress, 0.32, 0.62)
    const settle = segment(progress, 0.34, 0.7)

    for (const n of FIELD) {
      const alpha = n.keep ? 1 : 0.5 - fade * 0.46
      if (alpha <= 0.02) continue

      // Survivors ease toward their resting ring; the rest drift outward as they fade.
      const drift = n.keep ? settle : -fade * 0.12
      const x = (n.keep ? n.x + (n.tx - n.x) * settle : n.x + (n.x - 0.5) * -drift) * width
      const y = (n.keep ? n.y + (n.ty - n.y) * settle : n.y + (n.y - 0.5) * -drift) * height

      ctx.globalAlpha = alpha
      ctx.fillStyle = n.colour
      ctx.beginPath()
      ctx.arc(x, y, n.r * (n.keep ? 1 + settle * 0.5 : 1), 0, Math.PI * 2)
      ctx.fill()
    }
    ctx.globalAlpha = 1
  }, [progress])

  return <canvas ref={canvasRef} className={styles.canvas} aria-hidden="true" />
}

export function GraphReduce() {
  return (
    <PinnedSequence steps={3} label="Reducing the case" ground="obsidian" id="reduce">
      {(progress) => {
        const opening = segment(progress, 0, 0.28)
        const reducing = segment(progress, 0.34, 0.66)
        const propagating = segment(progress, 0.7, 1)

        const nodeCount = Math.round(SWARM - reducing * (SWARM - SURVIVORS))
        const typeCount = Math.round(
          graphCounts.all.types.length -
            reducing * (graphCounts.all.types.length - graphCounts.significant.types.length)
        )

        return (
          <div className={styles.wrap}>
            <Field progress={progress} />

            <div className={styles.overlay}>
              <header className={styles.head}>
                <p className={styles.eyebrow}>Reduction</p>
                <h2 data-state={reducing > 0.5 ? "after" : "before"}>
                  {reducing > 0.5 ? "Then you mark what matters." : "Every fact in the matter."}
                </h2>
                <p className={styles.lede} data-shown={opening > 0.2 || undefined}>
                  {reducing > 0.5
                    ? "The case narrows with you, and it stays narrowed — across the graph, the timeline, the map and the table."
                    : "All of it true. All of it sourced. None of it a case."}
                </p>
              </header>

              <dl className={styles.counters}>
                <div>
                  <dt>Entities</dt>
                  <dd>{nodeCount.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Types</dt>
                  <dd>{typeCount}</dd>
                </div>
              </dl>

              <ul className={styles.lenses} data-shown={propagating > 0.15 || undefined}>
                {["Graph", "Timeline", "Map", "Table"].map((lens) => (
                  <li key={lens}>
                    <span>{lens}</span>
                    <em>narrowed</em>
                  </li>
                ))}
              </ul>

              <p className={styles.caption}>Representative density — illustrative case data</p>
            </div>
          </div>
        )
      }}
    </PinnedSequence>
  )
}
