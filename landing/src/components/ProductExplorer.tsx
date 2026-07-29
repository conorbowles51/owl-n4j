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
    body: "See how people, organisations, accounts, events, and communications connect across every source in the case. Select any object to inspect the facts and files behind it.",
  },
  {
    id: "timeline",
    label: "Timeline",
    shortcut: "02",
    image: "/product/loupe-timeline-demo.png",
    alt: "Loupe timeline showing transactions and communications from the same connected case",
    title: "Test the chronology.",
    body: "Put transactions, messages, calls, documents, and other events on one timeline. Filter to the people or entities that matter without rebuilding the sequence by hand.",
  },
  {
    id: "evidence",
    label: "Evidence",
    shortcut: "03",
    image: "/product/loupe-evidence-demo.png",
    alt: "Loupe evidence workspace listing processed case files with source details and summaries",
    title: "Keep the source in reach.",
    body: "Work from the original material and its extracted facts together. Every useful claim keeps its route back to the file, page, passage, record, or timestamp it came from.",
  },
  {
    id: "agent",
    label: "Agent",
    shortcut: "04",
    image: "/product/loupe-agent-demo.png",
    alt: "Loupe agent creating a structured table from case evidence",
    title: "Ask for work, not just prose.",
    body: "Query the full case or a focused Loupe, then turn the result into tables, timelines, charts, and reviewable artifacts that remain part of the investigation.",
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
    <section className="story-section workspace-story" id="workspace">
      <div className="story-grid" aria-hidden="true" />
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">One model, many perspectives</p>
            <h2>Work the same case from every angle.</h2>
          </div>
          <p>
            The graph, timeline, evidence library, financial views, and agent all read from the
            same underlying case. Changing the view never changes the facts beneath it.
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
