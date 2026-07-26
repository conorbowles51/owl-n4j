import type { CSSProperties } from "react"
import { Reveal } from "../lib/Reveal"

type PreviewMode = "evidence" | "graph" | "timeline" | "agent"

type ProductStageItem = {
  key: PreviewMode
  number: string
  label: string
  body: string
  meta: string
  image: string
  alt: string
}

const stages: ProductStageItem[] = [
  {
    key: "evidence",
    number: "01",
    label: "Ingest every form of evidence",
    body: "Upload and process case material while preserving the original file, folder and source context.",
    meta: "Evidence workspace",
    image: "/product/loupe-evidence-demo.png",
    alt: "Loupe evidence workspace showing processed case documents, folder navigation and the selected interview document details.",
  },
  {
    key: "graph",
    number: "02",
    label: "Compile the case, do not prompt it",
    body: "Resolve people, organisations, locations, events and records into a persistent knowledge graph.",
    meta: "Graph view",
    image: "/product/loupe-graph-demo.png",
    alt: "Loupe graph view showing connected people, organisations, transactions and locations with Victoria Blackwood's details open.",
  },
  {
    key: "timeline",
    number: "03",
    label: "Rebuild what happened",
    body: "Order events from across the case, filter the chronology and open the evidence behind each entry.",
    meta: "Timeline view",
    image: "/product/loupe-timeline-demo.png",
    alt: "Loupe timeline showing source-backed transactions and communications with an email event selected.",
  },
  {
    key: "agent",
    number: "04",
    label: "Build work, not just answers",
    body: "Use case-scoped tools to examine evidence and build focused, reviewable artifacts that persist.",
    meta: "Agent workspace",
    image: "/product/loupe-agent-demo.png",
    alt: "Loupe AI Agent creating a focused table of the three largest transactions in a fictional case.",
  },
]

export function ProductStage() {
  return (
    <section className="product-section" id="platform">
      <div className="container product-inner">
        <Reveal className="section-heading product-heading">
          <p className="section-index">01 / Product</p>
          <h2>One case. Every investigative view.</h2>
          <p>
            Loupe keeps one case model beneath every workspace. Change the lens without
            fragmenting the evidence, repeating the work or losing the path back to source.
          </p>
        </Reveal>

        <div className="product-case-stack">
          <span className="product-case-thread" aria-hidden="true" />
          {stages.map((item, index) => (
            <article
              className={`product-case-card product-mode-${item.key}`}
              key={item.key}
              style={
                {
                  "--stack-index": index,
                  "--stack-depth": stages.length - index,
                } as CSSProperties
              }
            >
              <Reveal className="product-case-reveal" delay={Math.min(index * 0.04, 0.12)}>
                <span className="product-case-node" aria-hidden="true">
                  <i />
                  {item.number}
                </span>

                <span className="product-case-file-tab" aria-hidden="true">
                  <b>{item.number}</b>
                  <i>{item.meta}</i>
                </span>

                <div className="product-case-window">
                  <div className="product-case-capture">
                    <img
                      src={item.image}
                      alt={item.alt}
                      width="2558"
                      height="1265"
                      decoding="async"
                      loading={index < 2 ? "eager" : "lazy"}
                      fetchPriority={index === 0 ? "high" : "auto"}
                    />
                    <span className="product-case-matte" aria-hidden="true" />
                    <span className="product-case-scan" aria-hidden="true" />

                    <div className="product-case-copy">
                      <div>
                        <span>
                          {item.number} / {item.meta}
                        </span>
                        <h3>{item.label}</h3>
                        <p>{item.body}</p>
                      </div>
                      <a href={item.image} target="_blank" rel="noreferrer">
                        View full capture <i aria-hidden="true">&#8599;</i>
                      </a>
                    </div>

                    <span className="product-case-edge" aria-hidden="true" />
                  </div>
                </div>
              </Reveal>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
