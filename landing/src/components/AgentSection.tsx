import { Reveal } from "../lib/Reveal"

const agentCapabilities = [
  {
    title: "Investigates visibly",
    body: "Every run exposes its investigation trail: the tools used, the results returned and the evidence consulted.",
  },
  {
    title: "Builds work you keep",
    body: "Graphs, tables, charts, maps, reports and Loupes persist as case artifacts instead of disappearing into chat history.",
  },
  {
    title: "Tests both directions",
    body: "Ask for what supports a hypothesis—and what contradicts it—before the team decides what survives scrutiny.",
  },
  {
    title: "Respects the frame",
    body: "Case-scoped, read-only tools, bounded runs, visible citations and cost attribution keep the investigator in control.",
  },
]

export function AgentSection() {
  return (
    <section className="agent-section" id="agent">
      <div className="container">
        <Reveal className="agent-heading">
          <p className="section-index">05 / Agentic investigation</p>
          <h2>
            An agent that does.
            <br />
            <span>Not a chatbot that answers.</span>
          </h2>
          <p>
            Ask a simple question and get a cited answer. Describe a theory and the agent can search,
            cross-reference, query and build the durable work product needed to test it.
          </p>
        </Reveal>

        <div className="agent-layout">
          <Reveal className="agent-capture" delay={0.12}>
            <div className="product-capture-bar">
              <span>
                <i aria-hidden="true" />
                Actual product view
              </span>
              <strong>Agent artifacts</strong>
              <small>Fictional demonstration case</small>
            </div>
            <div className="agent-image">
              <img
                src="/product/loupe-agent-demo.png"
                alt="Loupe Agent showing a cited investigation response and a persistent transaction table artifact generated from case evidence."
                width="2558"
                height="1265"
                loading="lazy"
                decoding="async"
              />
            </div>
            <div className="product-caption">
              <span>Work product, not chat residue</span>
              <p>
                The agent builds a focused transaction table beside its reasoning so the result can
                be reviewed, exported and reused.
              </p>
              <a href="/product/loupe-agent-demo.png" target="_blank" rel="noreferrer">
                View full capture <i aria-hidden="true">↗</i>
              </a>
            </div>
          </Reveal>

          <div className="agent-capabilities">
            {agentCapabilities.map((capability, index) => (
              <Reveal as="article" delay={0.08 + index * 0.055} key={capability.title}>
                <span>0{index + 1}</span>
                <h3>{capability.title}</h3>
                <p>{capability.body}</p>
              </Reveal>
            ))}
          </div>
        </div>

        <Reveal className="agent-thesis">
          <span>Question-answering AI tells you about the evidence.</span>
          <strong>An agent with tools produces the work.</strong>
        </Reveal>
      </div>
    </section>
  )
}
