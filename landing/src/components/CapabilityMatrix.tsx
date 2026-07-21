import { Reveal } from "../lib/Reveal"

const capabilities = [
  {
    number: "01",
    title: "Connect anything",
    body: "Bring unstructured and structured sources together without flattening the context that makes them useful.",
    visual: "sources",
  },
  {
    number: "02",
    title: "Traverse relationships",
    body: "Move from a person to a document, transaction, event or location in a single connected model.",
    visual: "graph",
  },
  {
    number: "03",
    title: "Rebuild chronology",
    body: "Turn scattered dates and timestamps into an ordered, filterable account of what happened.",
    visual: "timeline",
  },
  {
    number: "04",
    title: "Follow movement",
    body: "Place events and entities in geographic context to reveal routes, clusters and converging activity.",
    visual: "map",
  },
  {
    number: "05",
    title: "Trace value",
    body: "Explore financial relationships and flows while preserving the records behind every connection.",
    visual: "flow",
  },
  {
    number: "06",
    title: "Ask with evidence",
    body: "Use natural language to explore the material and move directly from an answer to its supporting source.",
    visual: "answer",
  },
]

function CapabilityVisual({ type }: { type: string }) {
  if (type === "sources") {
    return <div className="cap-source-stack" aria-hidden="true"><i /><i /><i /><span>PDF</span><b>CSV</b></div>
  }
  if (type === "graph") {
    return <div className="cap-mini-graph" aria-hidden="true"><i /><i /><i /><i /><span /><span /><span /></div>
  }
  if (type === "timeline") {
    return <div className="cap-timeline" aria-hidden="true"><span /><i /><i /><b /><i /></div>
  }
  if (type === "map") {
    return <div className="cap-map" aria-hidden="true"><svg viewBox="0 0 220 100"><path d="M8 74C40 12 83 92 112 42s61 20 100-22" /><circle cx="54" cy="54" r="5" /><circle cx="114" cy="39" r="5" /><circle cx="187" cy="29" r="5" /></svg></div>
  }
  if (type === "flow") {
    return <div className="cap-flow" aria-hidden="true"><span>€</span><i /><b>£</b><i /><strong>$</strong></div>
  }
  return <div className="cap-answer" aria-hidden="true"><span /><span /><span /><b>↗</b></div>
}
export function CapabilityMatrix() {
  return (
    <section className="capabilities-section" id="capabilities">
      <div className="container">
        <Reveal className="section-heading section-heading-split">
          <div>
            <p className="section-index">02 / Capabilities</p>
            <h2>From raw material<br />to clear direction.</h2>
          </div>
          <p>
            Loupe is not another place to store information. It is the layer that makes everything
            you already have understandable together.
          </p>
        </Reveal>
        <div className="capability-grid">
          {capabilities.map((capability, index) => (
            <Reveal
              as="article"
              className={`capability capability-${capability.visual}`}
              delay={(index % 3) * 0.08}
              key={capability.title}
            >
              <div className="capability-topline">
                <span>{capability.number}</span>
                <i aria-hidden="true" />
              </div>
              <CapabilityVisual type={capability.visual} />
              <h3>{capability.title}</h3>
              <p>{capability.body}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
