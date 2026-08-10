import {
  agentCaveat,
  agentTrail,
  chartMonths,
  chartSource,
  chartTotal,
  clarification,
} from "../../data/case"
import { useIsNarrow } from "../../lib/useMediaQuery"
import { Reveal } from "../primitives/Reveal"
import styles from "./AgentDialogue.module.css"

const PAYMENTS_QUESTION = "Show me every payment from GlobalTech to Nexus Trading in 2023."

const payments = chartMonths.filter((m) => m.amount > 0)
const maxAmount = Math.max(...chartMonths.map((m) => m.amount))

const euro = (n: number) => `€${n.toLocaleString("en-GB")}`

/** Every payment in the series is a whole number of thousands. */
const euroShort = (n: number) => `€${Math.round(n / 1000)}k`

const CHART_LABEL = `Monthly payments from GlobalTech Industries to Nexus Trading Ltd, 2023: ${payments
  .map((p) => `${p.month} ${euro(p.amount)}`)
  .join(", ")} — ${euro(chartTotal)} in total.`

/**
 * The agent's answer, drawn rather than screenshotted so the bars stay crisp at
 * every DPI. Single series in the product's financial colour; zero months keep
 * their slot so the rhythm of the payments reads as part of the answer.
 */
function PaymentsChart() {
  const narrow = useIsNarrow()

  // Two fixed geometries instead of one scaled viewBox: SVG type shrinks with
  // the box, and the wide layout's labels fall below legibility at 390px.
  const W = narrow ? 352 : 600
  const H = narrow ? 172 : 210
  const padTop = narrow ? 14 : 28
  const padBottom = narrow ? 24 : 28
  const showValues = !narrow

  const baseline = H - padBottom
  const plotH = baseline - padTop
  const slot = W / chartMonths.length
  const barW = Math.min(30, slot * 0.62)

  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={CHART_LABEL}>
      <line className={styles.chartBaseline} x1="0" y1={baseline} x2={W} y2={baseline} />
      {chartMonths.map((m, i) => {
        const x = i * slot + (slot - barW) / 2
        if (m.amount === 0) {
          return (
            <rect
              key={m.month}
              className={styles.chartZero}
              x={x}
              y={baseline - 2}
              width={barW}
              height={2}
            />
          )
        }
        const h = Math.round((m.amount / maxAmount) * plotH)
        return (
          <g key={m.month}>
            <rect className={styles.chartBar} x={x} y={baseline - h} width={barW} height={h} rx="2" />
            {showValues ? (
              <text
                className={styles.chartValue}
                x={x + barW / 2}
                y={baseline - h - 8}
                textAnchor="middle"
                fontSize={12}
              >
                {euroShort(m.amount)}
              </text>
            ) : null}
          </g>
        )
      })}
      {chartMonths.map((m, i) => (
        <text
          key={m.month}
          className={styles.chartMonth}
          x={i * slot + slot / 2}
          y={H - 8}
          textAnchor="middle"
          fontSize={narrow ? 10.5 : 11}
        >
          {m.month}
        </text>
      ))}
    </svg>
  )
}

/**
 * Two exchanges from the same session, each complete in itself: the first is
 * the clarifying-question beat, the second the receipted answer. Then the
 * honesty beat, then the exported work product at full width. Component-built —
 * designed landing-page UI, not a screenshot imitation — so the type stays
 * legible at any width.
 */
export function AgentDialogue() {
  return (
    <section className={styles.section} id="agent" aria-labelledby="agent-dialogue-heading">
      <div className={styles.wrap}>
        <header className={styles.head}>
          <p className={styles.eyebrow}>Interrogation</p>
          <h2 id="agent-dialogue-heading">Ask in English. Every answer carries receipts.</h2>
          <p className={styles.lede}>
            The agent plans its own search of the case model, asks before it assumes, and returns
            figures that carry the file and page they came from.
          </p>
        </header>

        <div className={styles.exchanges}>
          {/* ------------------------------------------- exchange 1: it asks */}
          <div className={styles.thread}>
            <p className={styles.exchangeLabel}>Exchange 01</p>

            <Reveal>
              <div className={styles.turn} data-speaker="analyst">
                <p className={styles.speaker}>Analyst</p>
                <p className={styles.bubble}>{clarification.question}</p>
              </div>
            </Reveal>

            <Reveal delay={90}>
              <div className={styles.turn} data-speaker="agent">
                <p className={styles.speaker}>Agent</p>
                <div className={`${styles.bubble} ${styles.clarify}`}>
                  <p className={styles.clarifyLabel}>Clarifying question</p>
                  <p className={styles.ask}>{clarification.ask}</p>
                  <ul className={styles.options}>
                    {clarification.options.map((option) => (
                      <li key={option} data-chosen={option === clarification.chosen || undefined}>
                        {option}
                      </li>
                    ))}
                  </ul>
                </div>
                <p className={styles.clarifyNote}>It asks. It does not guess.</p>
              </div>
            </Reveal>

            <Reveal delay={150}>
              <div className={styles.turn} data-speaker="analyst">
                <p className={styles.bubble}>{clarification.chosen}.</p>
              </div>
            </Reveal>
          </div>

          {/* --------------------------------------- exchange 2: the receipt */}
          <div className={styles.thread}>
            <p className={styles.exchangeLabel}>Exchange 02</p>

            <Reveal delay={120}>
              <div className={styles.turn} data-speaker="analyst">
                <p className={styles.speaker}>Analyst</p>
                <p className={styles.bubble}>{PAYMENTS_QUESTION}</p>
              </div>
            </Reveal>

            <Reveal delay={210}>
              <div className={styles.turn} data-speaker="agent">
                <p className={styles.speaker}>Agent</p>
                <div className={`${styles.bubble} ${styles.answer}`}>
                  <p className={styles.total}>{euro(chartTotal)}</p>
                  <p className={styles.totalNote}>
                    {payments.length} payments from GlobalTech Industries to Nexus Trading Ltd —
                    March to December 2023.
                  </p>
                  <PaymentsChart />
                  <p className={styles.answerMeta}>
                    <span className="receipt">{chartSource}</span>
                    <span className={styles.trail}>
                      Investigation trail — {agentTrail.steps} steps · {agentTrail.seconds}s
                    </span>
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </div>

        <Reveal delay={260}>
          {/* Honesty is part of the pitch: the agent's own limit, verbatim. */}
          <div className={styles.caveatBeat}>
            <p className={styles.caveatLead}>
              Asked later whether those payments bought the €2.45 million Monaco property —{" "}
              <span className="receipt">05_property_records_monaco.pdf, p.1</span> — the agent
              answered:
            </p>
            <blockquote className={styles.caveat}>
              <p>{agentCaveat}</p>
              <cite>The agent, stating the limit of its own answer</cite>
            </blockquote>
          </div>
        </Reveal>

        <p className={styles.caption}>Illustrative case data</p>

        {/* ------------------------------------------------- work product */}
        <div className={styles.product}>
          <Reveal delay={140}>
            <p className={styles.productKicker}>The work product</p>
            <p className={styles.productLine}>
              Answers become exportable artifacts. Another exchange from the same case — asked where
              the two interviews disagree, the agent returned this table, and every row quotes the
              passage it stands on.
            </p>
            <figure className={styles.reportFrame}>
              <div className={styles.reportCrop}>
                <picture>
                  <source media="(max-width: 767px)" srcSet="/product/plates/agent-table-m.webp" />
                  <img
                    src="/product/plates/agent-table.webp"
                    alt="A Loupe table artifact titled 'Conflicts in Chen and Okonkwo Interviews', each conflict row carrying a verbatim quote and its source citation, with CSV and table export controls."
                    loading="lazy"
                    decoding="async"
                  />
                </picture>
              </div>
              <figcaption>Illustrative case data</figcaption>
            </figure>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
