import { useState, type KeyboardEvent } from "react"
import { Reveal } from "../lib/Reveal"

const productViews = [
  {
    id: "graph",
    label: "Graph",
    shortcut: "01",
    image: "/product/loupe-graph-demo.png",
    alt: "Loupe graph view connecting people, organisations, transactions, communications, and source evidence",
    title: "Follow the relationships.",
    body: "People, organisations, accounts, events and communications, connected across every source in the case. Select any object to see the facts behind it and the files those facts came from.",
  },
  {
    id: "timeline",
    label: "Timeline",
    shortcut: "02",
    image: "/product/loupe-timeline-demo.png",
    alt: "Loupe timeline showing transactions and communications from the same connected case",
    title: "Test the chronology.",
    body: "Transactions, messages, calls and documents on one timeline, in the timezone the matter needs. Filter to the people who matter without rebuilding the sequence by hand.",
  },
  {
    id: "evidence",
    label: "Evidence",
    shortcut: "03",
    image: "/product/loupe-evidence-demo.png",
    alt: "Loupe evidence workspace listing processed case files with source details and summaries",
    title: "Keep the source in reach.",
    body: "The original material and the facts extracted from it, side by side. Every claim keeps its route back to the file, page, passage, record or timestamp it came from.",
  },
  {
    id: "agent",
    label: "Agent",
    shortcut: "04",
    image: "/product/loupe-agent-demo.png",
    alt: "Loupe agent creating a structured table from case evidence",
    title: "Ask for work, not just prose.",
    body: "Question-answering tells you about your evidence. An agent with tools across the case model produces the work — grouped transactions, tables, timelines and charts that stay part of the investigation.",
  },
]

export function ProductExplorer() {
  const [activeId, setActiveId] = useState(productViews[0].id)
  const activeView = productViews.find((view) => view.id === activeId) ?? productViews[0]

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return
    event.preventDefault()

    const currentIndex = productViews.findIndex((view) => view.id === activeId)
    let nextIndex = currentIndex

    if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + productViews.length) % productViews.length
    } else if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % productViews.length
    } else if (event.key === "Home") {
      nextIndex = 0
    } else if (event.key === "End") {
      nextIndex = productViews.length - 1
    }

    const nextView = productViews[nextIndex]
    setActiveId(nextView.id)
    document.getElementById(`product-tab-${nextView.id}`)?.focus()
  }

  return (
    <section className="sec sec-paper" id="workspace">
      <div className="container">
        <Reveal className="sec-head">
          <p className="eyebrow">Perspectives</p>
          <h2>One case, worked from every angle.</h2>
          <p className="sec-lede">
            Graph, timeline, evidence and agent are not separate tools. They are perspectives on one
            structure, which is why a finding in one is the same object in another.
          </p>
        </Reveal>

        <Reveal className="product-explorer" delay={0.08}>
          <div className="product-explorer-tabs" role="tablist" aria-label="Loupe product views">
            {productViews.map((view) => {
              const selected = view.id === activeView.id
              return (
                <button
                  id={`product-tab-${view.id}`}
                  key={view.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-controls={`product-panel-${view.id}`}
                  tabIndex={selected ? 0 : -1}
                  className={selected ? "is-active" : ""}
                  onClick={() => setActiveId(view.id)}
                  onKeyDown={onTabKeyDown}
                >
                  <span>{view.shortcut}</span>
                  {view.label}
                </button>
              )
            })}
          </div>

          <div
            className="product-explorer-window"
            id={`product-panel-${activeView.id}`}
            role="tabpanel"
            aria-labelledby={`product-tab-${activeView.id}`}
          >
            <div className="product-window-bar" aria-hidden="true">
              <span>
                <i />
                <i />
                <i />
              </span>
              <b>loupe / active case / {activeView.id}</b>
              <em>Source-linked</em>
            </div>
            <div className="product-explorer-image">
              <img
                key={activeView.id}
                src={activeView.image}
                alt={activeView.alt}
                decoding="async"
              />
            </div>
            <div className="product-explorer-caption">
              <span>{activeView.shortcut}</span>
              <div>
                <h3>{activeView.title}</h3>
                <p>{activeView.body}</p>
              </div>
              <small>Interface shown with illustrative case data</small>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
