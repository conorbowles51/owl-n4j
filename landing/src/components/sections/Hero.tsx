import type { CSSProperties } from "react"
import { entityColours } from "../../data/case"
import { scaleLine } from "../../data/claims"
import styles from "./Hero.module.css"

interface HeroProps {
  onContact: () => void
}

/**
 * One dot in the hero constellation. Coordinates are percentages of the field,
 * hand-composed rather than force-directed: the copy owns the left half, so
 * density builds toward the right edge and the fade mask does the rest.
 */
interface FieldNode {
  id: string
  /** Key of `entityColours` — the dot takes the product's own palette. */
  type: string
  x: number
  y: number
  /** Dot diameter, px. 8–42 by importance in the case. */
  size: number
  label?: string
  /** Label tier. `sm` labels drop out below 768px where they cannot fit. */
  tier?: "lg" | "md"
  /** The product's selection state: accent ring, brightest label. */
  selected?: boolean
  /** Background texture only — dimmed, no glow, never labelled. */
  dim?: boolean
}

/**
 * Every name, amount and date below is from `case.ts` — the registry, the bank
 * statement, the invoices, the comms extraction. Array order is settle order:
 * the selected node lands first, then the money path, then the cast, then
 * ambience.
 */
const fieldNodes: FieldNode[] = [
  // The money path.
  { id: "nexus", type: "Organization", x: 80, y: 40, size: 42, label: "Nexus Trading Ltd", tier: "lg", selected: true },
  { id: "globaltech", type: "Organization", x: 71, y: 15, size: 30, label: "GlobalTech Industries", tier: "md" },
  { id: "sapphire", type: "Organization", x: 88, y: 66, size: 26, label: "Sapphire Investments Ltd", tier: "md" },
  { id: "cayman-bank", type: "Organization", x: 92, y: 14, size: 22, label: "Cayman National Bank", tier: "md" },
  { id: "fcib", type: "Account", x: 91, y: 30, size: 20, label: "FCIB-7729384756", tier: "md" },

  // The people.
  { id: "blackwood", type: "Person", x: 89, y: 46, size: 24, label: "Victoria Blackwood", tier: "md" },
  { id: "chen", type: "Person", x: 70, y: 55, size: 24, label: "Marcus Chen", tier: "md" },

  // The six dated payments, per `invoiceDescriptions`, arcing in toward Nexus.
  { id: "t-mar", type: "Transaction", x: 61, y: 24, size: 12, label: "€125,000 · 15 Mar" },
  { id: "t-may", type: "Transaction", x: 65, y: 34, size: 12, label: "€180,000 · 22 May" },
  { id: "t-jul", type: "Transaction", x: 61, y: 43, size: 11, label: "€95,000 · 8 Jul" },
  { id: "t-sep", type: "Transaction", x: 68, y: 45, size: 13, label: "€210,000 · 30 Sep" },
  { id: "t-nov", type: "Transaction", x: 74, y: 30, size: 12, label: "€150,000 · 12 Nov" },
  { id: "t-dec", type: "Transaction", x: 76, y: 24, size: 14, label: "€275,000 · 20 Dec" },

  // Supporting cast.
  { id: "okonkwo", type: "Person", x: 63, y: 74, size: 14, label: "David Okonkwo" },
  { id: "emerald", type: "Organization", x: 94, y: 55, size: 16, label: "Emerald Holdings SA" },
  { id: "call", type: "Communication", x: 78, y: 68, size: 14, label: "Recorded call · 4:29" },
  { id: "email", type: "Document", x: 64, y: 63, size: 12, label: "04_email_evidence.pdf" },
  { id: "handle", type: "Cyberidentity", x: 81, y: 80, size: 14, label: "+44 7700 900XXX" },
  { id: "cayman", type: "Location", x: 96, y: 22, size: 12, label: "Cayman Islands" },
  { id: "monaco", type: "Location", x: 93, y: 78, size: 12, label: "Monaco" },
  { id: "bvi", type: "Location", x: 73, y: 87, size: 12, label: "Tortola, BVI" },
  { id: "freezing-order", type: "Legalaction", x: 59, y: 85, size: 12, label: "CL-2024-000892" },

  // Ambience. The left tail sits mostly behind the copy mask — it reads as the
  // case receding into the dark, and surfaces again in the <1280 band layout.
  { id: "a1", type: "Communication", x: 46, y: 18, size: 8, dim: true },
  { id: "a2", type: "Location", x: 52, y: 32, size: 9, dim: true },
  { id: "a3", type: "Person", x: 44, y: 48, size: 8, dim: true },
  { id: "a4", type: "Transaction", x: 50, y: 62, size: 9, dim: true },
  { id: "a5", type: "Document", x: 46, y: 78, size: 8, dim: true },
  { id: "a6", type: "Transaction", x: 55, y: 12, size: 8, dim: true },
  { id: "a7", type: "Organization", x: 57, y: 44, size: 9, dim: true },
  { id: "a8", type: "Location", x: 54, y: 88, size: 8, dim: true },
  { id: "a9", type: "Communication", x: 61, y: 55, size: 8, dim: true },
  { id: "a10", type: "Document", x: 86, y: 88, size: 8, dim: true },
  { id: "a11", type: "Transaction", x: 96, y: 68, size: 9, dim: true },
  { id: "a12", type: "Person", x: 95, y: 8, size: 8, dim: true },
  { id: "a13", type: "Location", x: 67, y: 8, size: 8, dim: true },
]

const nodeById = new Map(fieldNodes.map((node) => [node.id, node]))

interface FieldEdge {
  x1: number
  y1: number
  x2: number
  y2: number
}

function link(a: string, b: string): FieldEdge {
  const from = nodeById.get(a)
  const to = nodeById.get(b)
  if (!from || !to) throw new Error(`Hero field edge references unknown node: ${a} → ${b}`)
  return { x1: from.x, y1: from.y, x2: to.x, y2: to.y }
}

/** The money path the page spends the rest of its length proving. */
const moneyEdges: FieldEdge[] = [
  link("globaltech", "nexus"),
  link("nexus", "sapphire"),
  link("nexus", "cayman-bank"),
]

/** Relationships the case files actually state — faint, texture not argument. */
const relationEdges: FieldEdge[] = [
  link("blackwood", "nexus"),
  link("chen", "globaltech"),
  link("nexus", "fcib"),
  link("chen", "call"),
  link("blackwood", "call"),
  link("chen", "handle"),
  link("chen", "email"),
  link("okonkwo", "chen"),
  link("sapphire", "monaco"),
  link("nexus", "bvi"),
]

/** Drift periods, seconds. Deliberately co-prime-ish so the field never beats. */
const driftDurations = [9, 12.5, 10.5, 14, 11, 13]

export function Hero({ onContact }: HeroProps) {
  return (
    <section className={styles.hero} id="top">
      <div className={styles.grid} aria-hidden="true" />

      <div className={styles.copy}>
        <p className={styles.eyebrow}>Investigation platform for serious casework</p>
        <h1>Query the whole case.</h1>
        <p className={styles.lede}>
          Loupe resolves phone extractions, documents, financial records and audio into one
          connected model of the case — so a question reaches all of it at once, and every answer
          carries the file, page and passage behind it.
        </p>

        <div className={styles.actions}>
          <button className={styles.primary} type="button" onClick={onContact}>
            Request a walkthrough
          </button>
          <a className={styles.ghost} href="#case">
            See it work a case
          </a>
        </div>

        <p className={styles.stat}>{scaleLine}</p>
      </div>

      {/* The case graph, rendered live rather than screenshotted: DOM circles and
          SVG hairlines stay crisp at any devicePixelRatio, which is the entire
          reason the bitmap plate is gone. Decorative — the copy carries the
          message, so the field is hidden from assistive tech. */}
      <div className={styles.field} aria-hidden="true">
        <div className={styles.fieldInner}>
          <svg className={styles.edges} viewBox="0 0 100 100" preserveAspectRatio="none">
            {relationEdges.map((edge, i) => (
              <line key={`r${i}`} className={styles.edge} {...edge} />
            ))}
            {moneyEdges.map((edge, i) => (
              <line key={`m${i}`} className={styles.edgeMoney} {...edge} />
            ))}
          </svg>

          {fieldNodes.map((node, i) => (
            <div
              key={node.id}
              className={[
                styles.node,
                node.selected ? styles.selected : "",
                node.dim ? styles.dim : "",
              ]
                .filter(Boolean)
                .join(" ")}
              data-drift={i % 3}
              style={
                {
                  left: `${node.x}%`,
                  top: `${node.y}%`,
                  width: node.size,
                  height: node.size,
                  "--settle-delay": `${100 + i * 38}ms`,
                  "--drift-dur": `${driftDurations[i % driftDurations.length]}s`,
                  "--drift-delay": `${-((i * 1.7) % 9)}s`,
                } as CSSProperties
              }
            >
              <div className={styles.orbit}>
                <span className={styles.dot} style={{ color: entityColours[node.type] }} />
                {node.label ? (
                  <span className={styles.label} data-tier={node.tier ?? "sm"}>
                    {node.label}
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className={styles.caption}>Illustrative case data</p>
    </section>
  )
}
