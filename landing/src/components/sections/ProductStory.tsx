import { FilmFrame } from "../FilmFrame"
import { ProviderLogo, type ProviderId } from "../ProviderLogo"
import { Reveal } from "../primitives/Reveal"

interface ProductStoryProps {
  onContact: () => void
}

const deployment = [
  ["01", "Complete tenant isolation", "Your Loupe application instance does not share its databases, queues or network boundary with another organisation."],
  ["02", "Deploy where the matter requires", "Choose the region your legal and operational requirements demand, including on-premises deployment."],
  ["03", "Access enforced per case", "Membership is verified on every route and investigator actions are recorded against the person who made them."],
  ["04", "Source-linked and auditable", "Every object carries the file, page, record or timestamp it came from, so findings return to the evidence."],
]

const providers: Array<{ id: ProviderId; name: string; descriptor: string }> = [
  { id: "openai", name: "OpenAI", descriptor: "Native connection" },
  { id: "anthropic", name: "Anthropic", descriptor: "Native connection" },
  { id: "gemini", name: "Gemini", descriptor: "Native connection" },
  { id: "deepseek", name: "DeepSeek", descriptor: "Native connection" },
]

export function ProductStory({ onContact }: ProductStoryProps) {
  return (
    <>
      <section className="film-section" id="film">
        <div className="container film-intro">
          <Reveal>
            <p className="section-index">The product, end to end</p>
            <h2>Watch a case<br />come into focus.</h2>
            <p>
              From a blank matter to a cited investigative report in sixty-three seconds. This is
              one path through Loupe—and only a glimpse of what the wider platform can do.
            </p>
          </Reveal>
        </div>
        <div className="film-stage">
          <FilmFrame
            eager
            className="film-frame-main"
            label="Loupe product film · Nexus Trading"
            poster="/films/loupe-product-film-poster.webp"
            webm="/films/loupe-product-film-web.webm"
            mp4="/films/loupe-product-film-web.mp4"
          />
        </div>
        <p className="film-caption">Illustrative case data · Interface shown at accelerated pace</p>
      </section>

      <section className="story-section story-section-light" id="evidence">
        <div className="container story-heading">
          <Reveal>
            <p className="section-index">01 · Evidence</p>
            <h2>Give every source its context.</h2>
            <p>
              Organise disclosures, interviews, bank records and phone material in one case.
              Processing profiles travel through the folder structure, so each source is read with
              the instructions that matter.
            </p>
          </Reveal>
        </div>

        <div className="container feature-row feature-row-wide">
          <Reveal>
            <FilmFrame
              label="Evidence processing and folder instructions"
              poster="/films/evidence-workflow-poster.webp"
              webm="/films/evidence-workflow.webm"
              mp4="/films/evidence-workflow.mp4"
            />
          </Reveal>
          <Reveal delay={80}>
            <div className="feature-copy">
              <p className="feature-number">01A</p>
              <h3>Structure before scale.</h3>
              <p>
                Folder-level context, mandatory extraction rules and special entity types make the
                processing pipeline explicit. Select a batch, process it, and watch entities and
                relationships resolve into the case model.
              </p>
              <ul>
                <li>Inherited case and folder instructions</li>
                <li>Documents, audio and structured records</li>
                <li>Visible processing state for every file</li>
              </ul>
            </div>
          </Reveal>
        </div>

        <div className="container feature-row feature-row-reverse">
          <Reveal>
            <FilmFrame
              label="Comprehensive, source-linked evidence summaries"
              poster="/films/evidence-intelligence-poster.webp"
              webm="/films/evidence-intelligence.webm"
              mp4="/films/evidence-intelligence.mp4"
            />
          </Reveal>
          <Reveal delay={80}>
            <div className="feature-copy">
              <p className="feature-number">01B</p>
              <h3>Read less. Know more.</h3>
              <p>
                Every processed source becomes a structured briefing: a full overview, the people
                and organisations involved, key dates, and the connections worth following. Every
                claim keeps its page citation beside it.
              </p>
              <ul>
                <li>Comprehensive overviews, not one-line abstracts</li>
                <li>Key entities, facts, dates and notable connections</li>
                <li>Page-level citations attached to every finding</li>
              </ul>
            </div>
          </Reveal>
        </div>

        <div className="container feature-row feature-row-search">
          <Reveal>
            <FilmFrame
              label="Search exact text across every document in the case"
              poster="/films/case-text-search-poster.webp"
              webm="/films/case-text-search.webm"
              mp4="/films/case-text-search.mp4"
            />
          </Reveal>
          <Reveal delay={80}>
            <div className="feature-copy">
              <p className="feature-number">01C</p>
              <h3>Find the exact words.</h3>
              <p>
                Change the evidence search from filenames to Text in case and search every
                processed document at once. Results arrive grouped by source, with the matching
                phrase highlighted and its page ready to open.
              </p>
              <ul>
                <li>Exact names, phrases, account numbers and identifiers</li>
                <li>Matches grouped by document and page</li>
                <li>Jump directly from a result to the original evidence</li>
              </ul>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="story-section story-section-dark" id="views">
        <div className="container story-heading story-heading-split">
          <Reveal>
            <p className="section-index">02 · Case views</p>
            <h2>Change the view.<br />Keep the case.</h2>
          </Reveal>
          <Reveal delay={80}>
            <p>
              The same connected evidence can be explored as a graph, chronology, map or table.
              Filters and the Significant layer stay with you, so changing perspective never means
              rebuilding the work.
            </p>
          </Reveal>
        </div>
        <div className="container views-film">
          <Reveal>
            <FilmFrame
              label="Graph, timeline, map and table views"
              poster="/films/case-views-poster.webp"
              webm="/films/case-views.webm"
              mp4="/films/case-views.mp4"
            />
          </Reveal>
        </div>
        <div className="container view-index" aria-label="Available case views">
          <span>Graph</span><span>Timeline</span><span>Map</span><span>Table</span>
        </div>
      </section>

      <section className="story-section story-section-paper" id="ai">
        <div className="container feature-row ai-feature-row">
          <Reveal>
            <div className="feature-copy feature-copy-large">
              <p className="section-index">03 · AI workspace</p>
              <h2>Ask in context.<br />Work in evidence.</h2>
              <p>
                Chat and notebook stay beside the case as you move. For deeper work, the Agent can
                search the graph, inspect documents, run safe read-only queries and build focused
                charts, tables, graphs and reports.
              </p>
              <div className="citation-line">
                <span>Answer</span><i />
                <span>Source</span><i />
                <span>Report</span>
              </div>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <FilmFrame
              label="Persistent AI chat, notebook, agent and report"
              poster="/films/ai-workspace-poster.webp"
              webm="/films/ai-workspace.webm"
              mp4="/films/ai-workspace.mp4"
            />
          </Reveal>
        </div>
      </section>

      <section className="deployment-section" id="deployment">
        <div className="container deployment-heading">
          <Reveal>
            <p className="section-index">04 · Deployment</p>
            <h2>Your evidence.<br />Your environment.</h2>
          </Reveal>
          <Reveal delay={80}>
            <div className="deployment-lede">
              <p>
                Each customer receives a dedicated Loupe application instance, hosted in the
                region—or on-premises environment—the matter requires.
              </p>
              <p className="deployment-provider-note">
                <span>Your provider, your choice</span>
                Connect the AI provider your organisation already trusts and uses. Loupe routes
                its AI workloads through that choice.
              </p>
            </div>
          </Reveal>
        </div>
        <div className="container deployment-grid">
          {deployment.map(([index, title, body], itemIndex) => (
            <Reveal key={title} delay={itemIndex * 55}>
              <article>
                <div className="deployment-card-topline">
                  <p className="deploy-index">{index}</p>
                  {itemIndex === 0 ? <span>Loupe infrastructure</span> : null}
                </div>
                {itemIndex === 0 ? (
                  <p className="deployment-card-statement">
                    One customer.<br />One Loupe instance.
                  </p>
                ) : null}
                <div className="deployment-card-copy">
                  <h3>{title}</h3>
                  <p>{body}</p>
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="provider-section" id="providers">
        <div className="container provider-heading">
          <Reveal>
            <p className="section-index">05 · AI providers</p>
            <h2>Bring your own<br />provider.</h2>
          </Reveal>
          <Reveal delay={80}>
            <div className="provider-lede">
              <p>
                Bring the AI provider your organisation already uses—or choose whichever provider
                best fits the matter. Connect your own account and route each workload deliberately.
              </p>
            </div>
          </Reveal>
        </div>

        <div className="container provider-directory">
          <Reveal>
            <div className="provider-directory-heading">
              <p>Supported out of the box</p>
              <span>04 native connections</span>
            </div>
          </Reveal>
          <div className="provider-grid">
            {providers.map((provider, index) => (
              <Reveal key={provider.id} delay={index * 55}>
                <article>
                  <div className={`provider-mark provider-mark-${provider.id}`}>
                    <ProviderLogo provider={provider.id} />
                  </div>
                  <div>
                    <h3>{provider.name}</h3>
                    <p>{provider.descriptor}</p>
                  </div>
                </article>
              </Reveal>
            ))}
          </div>
          <Reveal delay={110}>
            <p className="provider-footnote">
              Need a different provider? The model layer is designed to be extended without moving
              your case or rebuilding the evidence model.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="closing-section">
        <div className="closing-orbit" aria-hidden="true"><span /></div>
        <div className="container closing-inner">
          <Reveal>
            <p className="section-index">Private walkthrough</p>
            <h2>Bring the difficult case.</h2>
            <p>We will show you what Loupe can make visible—and the evidence behind every answer.</p>
            <button className="button button-primary button-large" type="button" onClick={onContact}>
              Request a walkthrough <span aria-hidden="true">↗</span>
            </button>
          </Reveal>
        </div>
      </section>
    </>
  )
}
