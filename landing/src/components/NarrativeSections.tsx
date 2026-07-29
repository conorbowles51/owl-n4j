import { Reveal } from "../lib/Reveal"

const evidenceLoads = [
  {
    number: "01",
    title: "Phone extractions",
    detail: "Multi-gigabyte devices and hundreds of thousands of events",
  },
  {
    number: "02",
    title: "Documents",
    detail: "Statements, returns, reports, filings, and correspondence",
  },
  {
    number: "03",
    title: "Financial records",
    detail: "Tens of thousands of transactions across accounts and entities",
  },
  {
    number: "04",
    title: "Recorded media",
    detail: "Hours of audio, video, images, and their timestamps",
  },
]

const sourceTypes = [
  ["Device data", "Calls · messages · apps"],
  ["Documents", "Pages · passages · records"],
  ["Financial", "Accounts · transfers · transactions"],
  ["Media", "Audio · video · photographs"],
]

const caseViews = ["Graph", "Timeline", "Map", "Table", "Financial", "Agent"]

const differences = [
  {
    label: "Case memory",
    generic: "The work lives in a conversation and fades with the session.",
    loupe: "A persistent case graph survives every query, handover, and review.",
  },
  {
    label: "Coverage",
    generic: "Retrieval selects a plausible sample, so you cannot see what it left out.",
    loupe: "Queries traverse the model of the case and return the complete matching set.",
  },
  {
    label: "Citations",
    generic: "An answer may point at a document.",
    loupe: "Each claim keeps the file, page, passage, record, or timestamp that supports it.",
  },
  {
    label: "Human judgment",
    generic: "Highlights and reasoning live outside the tool.",
    loupe: "Significance, Loupes, and findings become durable objects in the case.",
  },
  {
    label: "Confidentiality",
    generic: "Evidence enters a shared multi-tenant service.",
    loupe: "Each customer runs in an isolated, single-tenant instance.",
  },
  {
    label: "Model dependence",
    generic: "The language model is the product.",
    loupe: "Models are interchangeable components. The evidence layer is permanent.",
  },
]

export function ProblemSection() {
  return (
    <section className="story-section problem-story" id="problem">
      <div className="story-grid" aria-hidden="true" />
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">The evidence is connected</p>
            <h2>The tools are not.</h2>
          </div>
          <p>
            Serious casework arrives as a mix of files, devices, transactions, media, and
            communications. Most investigation tools still make teams open them one at a time.
          </p>
        </Reveal>

        <div className="problem-layout">
          <Reveal as="article" className="problem-thesis">
            <p className="problem-quote">
              One phone. One PDF. One spreadsheet.
              <strong>Every connection left in someone’s head.</strong>
            </p>
            <p>
              Those connections do not scale, survive staff turnover, or travel cleanly into a
              report. Loupe gives the case a structure that can be explored, shared, and carried
              into the final work without rebuilding the connections by hand.
            </p>
            <div className="problem-origin">
              <span>The result</span>
              <p>One workspace for the evidence, the reasoning, and the work product.</p>
            </div>
          </Reveal>

          <div className="evidence-load" aria-label="Evidence a complex case can contain">
            {evidenceLoads.map((item, index) => (
              <Reveal as="article" key={item.number} delay={index * 0.05}>
                <span>{item.number}</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

export function CaseModelStory() {
  return (
    <section className="story-section model-story" id="platform">
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">The layer beneath the answer</p>
            <h2>Evidence in. One connected model out.</h2>
          </div>
          <p>
            Loupe resolves people, organisations, accounts, locations, events, and transactions
            as evidence enters the case. Every object remains attached to its origin.
          </p>
        </Reveal>

        <Reveal className="model-system" delay={0.08}>
          <div className="model-system-top">
            <span>Case model / live structure</span>
            <span>
              <i />
              Source index healthy
            </span>
          </div>
          <div className="model-system-body">
            <div className="model-sources">
              <p>Mixed evidence</p>
              {sourceTypes.map(([title, detail], index) => (
                <div key={title}>
                  <span>0{index + 1}</span>
                  <p>
                    <strong>{title}</strong>
                    <small>{detail}</small>
                  </p>
                  <i aria-hidden="true" />
                </div>
              ))}
            </div>

            <div className="model-core" aria-label="Persistent Loupe case model">
              <svg viewBox="0 0 340 340" aria-hidden="true">
                <circle cx="170" cy="170" r="128" />
                <circle cx="170" cy="170" r="92" />
                <path d="M48 118 120 92 167 152 236 83 290 137" />
                <path d="M55 238 125 211 167 152 222 225 284 191" />
                <path d="m120 92 5 119 97 14 14-142" />
              </svg>
              <span className="model-node node-1" />
              <span className="model-node node-2" />
              <span className="model-node node-3" />
              <span className="model-node node-4" />
              <span className="model-node node-5" />
              <div>
                <small>Persistent</small>
                <strong>Case model</strong>
                <span>Entities · events · sources</span>
              </div>
            </div>

            <div className="model-views">
              <p>Investigation views</p>
              {caseViews.map((view, index) => (
                <span key={view} className={index === 0 ? "is-active" : ""}>
                  <i>0{index + 1}</i>
                  {view}
                </span>
              ))}
            </div>
          </div>
          <div className="model-system-foot">
            <p>
              <span>One fact</span>
              <strong>One identity across every source</strong>
            </p>
            <p>
              <span>One provenance path</span>
              <strong>File → page → passage → claim</strong>
            </p>
            <p>
              <span>One durable workspace</span>
              <strong>Built to outlive the conversation</strong>
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

export function LoupeWorkflowSection() {
  return (
    <section className="story-section loupe-workflow" id="workflow">
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">Human judgment, made durable</p>
            <h2>Find what matters. Bind it. Keep the reasoning.</h2>
          </div>
          <p>
            A Loupe is a focused, bonded collection of evidence around one finding, person, event,
            theory, or line of enquiry. It carries the conclusion and the proof together.
          </p>
        </Reveal>

        <div className="loupe-assembly" aria-label="How investigators build durable findings">
          <Reveal as="article" className="assembly-step assembly-source">
            <div className="assembly-index">
              <span>01</span>
              <p>Mark the signal</p>
            </div>
            <div className="assembly-card evidence-fragment">
              <div>
                <span>Source passage</span>
                <b>Significant</b>
              </div>
              <blockquote>
                “The transfer was approved after the call and before the account changed.”
              </blockquote>
              <p>
                Interview transcript <strong>p. 18</strong>
              </p>
            </div>
            <p>
              Investigators highlight a passage, event, transaction, relationship, or other fact
              without detaching it from its source.
            </p>
          </Reveal>

          <Reveal as="article" className="assembly-step assembly-loupe" delay={0.06}>
            <div className="assembly-index">
              <span>02</span>
              <p>Build the Loupe</p>
            </div>
            <div className="assembly-card loupe-object">
              <div className="loupe-object-ring" aria-hidden="true">
                <i />
                <i />
                <i />
              </div>
              <span>Focused enquiry</span>
              <h3>Approval and movement of funds</h3>
              <div>
                <p>
                  <strong>14</strong>
                  facts
                </p>
                <p>
                  <strong>6</strong>
                  sources
                </p>
                <p>
                  <strong>4</strong>
                  people
                </p>
              </div>
            </div>
            <p>
              Related evidence from several source types becomes a reusable object in the case,
              not a temporary list in someone’s notes.
            </p>
          </Reveal>

          <Reveal as="article" className="assembly-step assembly-output" delay={0.12}>
            <div className="assembly-index">
              <span>03</span>
              <p>Produce the finding</p>
            </div>
            <div className="assembly-card finding-object">
              <div>
                <span>Finding 03</span>
                <b>Ready for review</b>
              </div>
              <h3>The sequence is supported across communications and financial records.</h3>
              <ul>
                <li>Conclusion written</li>
                <li>Evidence path retained</li>
                <li>Timeline and table attached</li>
              </ul>
            </div>
            <p>
              Findings, tables, timelines, charts, and reports stay with the case so another
              investigator, lawyer, or reviewer can test them.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

export function DifferenceSection() {
  return (
    <section className="story-section difference-story" id="why-loupe">
      <div className="story-grid" aria-hidden="true" />
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">Why Loupe</p>
            <h2>More than a chat window for documents.</h2>
          </div>
          <p>
            A general AI assistant writes about the evidence it can retrieve. Loupe gives the AI a
            persistent structure for the entire case, then preserves the work that follows.
          </p>
        </Reveal>

        <Reveal className="difference-matrix" delay={0.08}>
          <div className="difference-matrix-head" aria-hidden="true">
            <span>What changes</span>
            <span>Document chat</span>
            <span>Loupe</span>
          </div>
          {differences.map((row) => (
            <div className="difference-matrix-row" key={row.label}>
              <strong>{row.label}</strong>
              <p data-label="Document chat">{row.generic}</p>
              <p data-label="Loupe">
                <i aria-hidden="true" />
                {row.loupe}
              </p>
            </div>
          ))}
        </Reveal>

        <Reveal as="p" className="difference-close">
          The language model can change. The case does not.
        </Reveal>
      </div>
    </section>
  )
}

export function ProofSection() {
  return (
    <section className="story-section proof-story" id="proof">
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">Built for serious casework</p>
            <h2>A case workspace designed to stand up to scrutiny.</h2>
          </div>
          <p>
            Loupe brings investigators, lawyers, and reviewers into the same source-linked view of
            the evidence—without flattening the case into a chat thread.
          </p>
        </Reveal>

        <div className="proof-layout">
          <Reveal className="proof-statement">
            <span>From first review to final finding</span>
            <p>
              Work across device data, documents, financial records, and media while keeping the
              reasoning and original material together.
            </p>
            <div className="proof-status">
              <i />
              Connected by design
            </div>
          </Reveal>

          <div className="proof-ledger">
            <Reveal as="article">
              <span>01</span>
              <div>
                <strong>One shared case model</strong>
                <p>
                  Everyone works from the same entities, events, relationships, and source
                  evidence.
                </p>
              </div>
            </Reveal>
            <Reveal as="article" delay={0.05}>
              <span>02</span>
              <div>
                <strong>Review without losing context</strong>
                <p>
                  Move from a finding to its supporting passage, transaction, record, or timestamp.
                </p>
              </div>
            </Reveal>
            <Reveal as="article" delay={0.1}>
              <span>03</span>
              <div>
                <strong>Work that survives handover</strong>
                <p>
                  Loupes, findings, timelines, and tables stay with the case so another person can
                  pick up the thread.
                </p>
              </div>
            </Reveal>
          </div>
        </div>

        <Reveal className="trust-rail">
          <div>
            <span>Privacy</span>
            <strong>Private workspace</strong>
            <p>Each customer runs in an isolated, single-tenant environment.</p>
          </div>
          <div>
            <span>Traceability</span>
            <strong>Source-linked findings</strong>
            <p>Keep a clear route from each conclusion back to the evidence that supports it.</p>
          </div>
          <div>
            <span>AI architecture</span>
            <strong>Model-flexible</strong>
            <p>Language models can change without rebuilding the case or losing prior work.</p>
          </div>
          <div>
            <span>Continuity</span>
            <strong>Durable case record</strong>
            <p>Investigative decisions and work products remain available for review and handover.</p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

export function ImpactSection() {
  return (
    <section className="story-section impact-story" id="impact">
      <div className="container">
        <Reveal className="story-heading story-heading-split">
          <div>
            <p className="section-index">Who Loupe is for</p>
            <h2>Built for teams carrying complex evidence.</h2>
          </div>
          <p>
            Loupe gives specialist teams a connected investigation workspace without the
            complexity of a large enterprise rollout.
          </p>
        </Reveal>

        <div className="impact-layout">
          <Reveal className="market-gap">
            <span>A practical middle ground</span>
            <h3>Whole-case capability without a heavyweight rollout.</h3>
            <p>
              Loupe sits between simple document viewers and large investigative-intelligence
              platforms. Bring mixed evidence into one case workspace and start working the
              connections.
            </p>
            <div className="market-spectrum" aria-hidden="true">
              <i />
              <span>Document viewers</span>
              <b>Loupe</b>
              <span>Enterprise platforms</span>
            </div>
          </Reveal>

          <Reveal className="market-entry" delay={0.08}>
            <span>A simpler way to get started</span>
            <ol>
              <li>
                <b>01</b>
                <p>
                  <strong>Start with a matter</strong>
                  Bring together the evidence your team already has.
                </p>
              </li>
              <li>
                <b>02</b>
                <p>
                  <strong>Keep it isolated</strong>
                  Run each customer in a dedicated single-tenant instance.
                </p>
              </li>
              <li>
                <b>03</b>
                <p>
                  <strong>Expand when useful</strong>
                  Add matters, collaborators, and investigation views as your needs grow.
                </p>
              </li>
            </ol>
          </Reveal>
        </div>

        <Reveal className="market-fit">
          <div>
            <span>Designed for</span>
            <h3>Investigators, forensic teams, and legal practitioners.</h3>
            <p>
              Especially teams handling fraud, criminal defence, disputes, and other
              evidence-heavy matters.
            </p>
          </div>
          <div>
            <span>Also suited to</span>
            <ul>
              <li>Financial-crime and fraud units</li>
              <li>Law enforcement and prosecutors</li>
              <li>Law firms and disputes teams</li>
              <li>Corporate investigations and compliance</li>
            </ul>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
