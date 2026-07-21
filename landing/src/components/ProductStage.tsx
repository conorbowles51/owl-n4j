import { useState, type CSSProperties } from "react"
import { Reveal } from "../lib/Reveal"

const stages = [
  {
    key: "ingest",
    number: "01",
    label: "Bring every source into view",
    body: "Documents, communications, media, locations and structured records enter one coherent workspace.",
    meta: "Unified intake",
  },
  {
    key: "connect",
    number: "02",
    label: "Reveal the relationships",
    body: "Loupe resolves people, organisations, accounts, places and events into an explorable network.",
    meta: "Connected model",
  },
  {
    key: "sequence",
    number: "03",
    label: "Rebuild what happened",
    body: "Move between graph, chronology, map, table and financial views without losing the underlying context.",
    meta: "Multiple lenses",
  },
  {
    key: "explain",
    number: "04",
    label: "Move from finding to proof",
    body: "Ask complex questions, preserve the reasoning path and return to the exact material behind each answer.",
    meta: "Source linked",
  },
]

const graphNodes = [
  { x: 145, y: 198, r: 13, type: "person", label: "M. Chen" },
  { x: 260, y: 112, r: 16, type: "company", label: "Northstar" },
  { x: 362, y: 202, r: 18, type: "focus", label: "Project Atlas" },
  { x: 490, y: 126, r: 12, type: "account", label: "AC-2049" },
  { x: 548, y: 258, r: 14, type: "location", label: "Dublin" },
  { x: 410, y: 322, r: 11, type: "event", label: "Meeting" },
  { x: 246, y: 294, r: 10, type: "document", label: "Memo 7" },
  { x: 105, y: 322, r: 9, type: "event", label: "Transfer" },
]

const graphEdges = [
  [0, 1], [0, 2], [0, 6], [1, 2], [1, 3], [2, 3], [2, 4], [2, 5], [2, 6], [3, 4], [4, 5], [5, 6], [6, 7],
]

export function ProductStage() {
  const [active, setActive] = useState(1)
  const stage = stages[active]

  return (
    <section className="product-section" id="platform">
      <div className="container">
        <Reveal className="section-heading product-heading">
          <p className="section-index">01 / Platform</p>
          <h2>One intelligence layer.<br />Every perspective.</h2>
          <p>
            Loupe keeps the same connected body of information beneath every view. Change the lens,
            not the truth you are looking at.
          </p>
        </Reveal>

        <div className="product-layout">
          <Reveal className="product-steps" delay={0.1}>
            {stages.map((item, index) => (
              <button
                key={item.key}
                type="button"
                className={`product-step ${active === index ? "is-active" : ""}`}
                aria-pressed={active === index}
                onClick={() => setActive(index)}
              >
                <span className="product-step-number">{item.number}</span>
                <span className="product-step-copy">
                  <strong>{item.label}</strong>
                  <small>{item.meta}</small>
                </span>
                <span className="product-step-marker" aria-hidden="true" />
              </button>
            ))}
          </Reveal>

          <Reveal className="product-window-wrap" delay={0.18}>
            <div className={`product-window product-mode-${stage.key}`}>
              <div className="window-chrome">
                <span className="window-mark" aria-hidden="true">
                  <i /><i /><b />
                </span>
                <div>
                  <strong>Project Atlas</strong>
                  <small>Connected workspace</small>
                </div>
                <div className="window-status">
                  <i /> Live model
                </div>
              </div>
              <div className="window-body">
                <aside className="window-rail" aria-label="Preview navigation">
                  {[
                    ["⌘", "Network"],
                    ["◷", "Timeline"],
                    ["⌖", "Map"],
                    ["▤", "Table"],
                    ["↗", "Financial"],
                  ].map(([icon, label], index) => (
                    <span className={index === active || (active === 3 && index === 0) ? "is-active" : ""} key={label}>
                      <b aria-hidden="true">{icon}</b>{label}
                    </span>
                  ))}
                </aside>
                <div className="source-drawer">
                  <div className="source-drawer-title">
                    <span>Sources</span><b>24</b>
                  </div>
                  {[
                    ["Q4 review.pdf", "118 pages"],
                    ["Messages export", "4,219 items"],
                    ["Transactions.csv", "842 rows"],
                    ["Field notes", "36 entries"],
                  ].map(([name, count], index) => (
                    <div className={`source-row ${index === active ? "is-active" : ""}`} key={name}>
                      <i aria-hidden="true" />
                      <span><strong>{name}</strong><small>{count}</small></span>
                    </div>
                  ))}
                </div>
                <div className="network-stage">
                  <div className="network-toolbar">
                    <span>Connected view</span>
                    <span className="network-filter">All sources⌄</span>
                  </div>
                  <svg className="network-graph" viewBox="0 0 650 410" role="img" aria-label="Connected information preview">
                    <defs>
                      <radialGradient id="graph-focus">
                        <stop offset="0" stopColor="#20c7c0" stopOpacity="0.95" />
                        <stop offset="1" stopColor="#0e5d67" stopOpacity="0.3" />
                      </radialGradient>
                    </defs>
                    <g className="graph-grid-lines">
                      {Array.from({ length: 8 }, (_, index) => <line x1="0" x2="650" y1={index * 58} y2={index * 58} key={`h-${index}`} />)}
                      {Array.from({ length: 11 }, (_, index) => <line y1="0" y2="410" x1={index * 65} x2={index * 65} key={`v-${index}`} />)}
                    </g>
                    <g className="graph-edges">
                      {graphEdges.map(([from, to], index) => (
                        <line
                          key={`${from}-${to}`}
                          x1={graphNodes[from].x}
                          y1={graphNodes[from].y}
                          x2={graphNodes[to].x}
                          y2={graphNodes[to].y}
                          style={{ "--edge-index": index } as CSSProperties}
                        />
                      ))}
                    </g>
                    <g className="graph-nodes">
                      {graphNodes.map((node, index) => (
                        <g className={`graph-node graph-node-${node.type}`} transform={`translate(${node.x} ${node.y})`} key={node.label}>
                          <circle r={node.r + 8} className="node-halo" />
                          <circle r={node.r} />
                          <text y={node.r + 20} textAnchor="middle">{node.label}</text>
                          {index === 2 && <circle r={node.r + 15} className="node-orbit" />}
                        </g>
                      ))}
                    </g>
                    <g className="timeline-overlay">
                      <line x1="74" y1="320" x2="580" y2="320" />
                      {[120, 226, 360, 486, 552].map((x, index) => (
                        <g transform={`translate(${x} 320)`} key={x}>
                          <circle r={index === 2 ? 7 : 4} />
                          <text y="26" textAnchor="middle">{["09:12", "11:48", "14:06", "16:22", "18:10"][index]}</text>
                        </g>
                      ))}
                    </g>
                  </svg>
                  <div className="source-citation">
                    <span>Source-linked finding</span>
                    <p>{stage.body}</p>
                    <small>Q4 review.pdf · p. 47 <b>Open source ↗</b></small>
                  </div>
                  <div className="view-readout">
                    <span>{stage.meta}</span>
                    <strong>{String(active + 1).padStart(2, "0")}</strong>
                  </div>
                </div>
              </div>
            </div>
            <p className="product-caption"><span>Live concept</span> One workspace, multiple analytical lenses.</p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
