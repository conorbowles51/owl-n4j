import {
  chartMonths,
  conflicts,
  invoiceDescriptions,
  passThrough,
  recitedAmounts,
  recording,
  transcript,
} from "../../data/case"
import { segment } from "../../lib/useScrollProgress"
import { PinnedSequence } from "../primitives/PinnedSequence"
import styles from "./Convergence.module.css"

const SHORT = (n: number) => `€${(n / 1000).toFixed(0)}k`
const peak = Math.max(...chartMonths.map((m) => m.amount))

/** Splits the 00:35 turn so each recited amount can be marked individually. */
function RecitedTurn({ lit }: { lit: number }) {
  const turn = transcript.find((t) => t.at === "00:35")!
  const [before, list] = turn.text.split("—").map((s) => s.trim())
  const parts = list.replace(/\.$/, "").split(",").map((s) => s.trim())

  return (
    <p className={styles.turnText}>
      {before} —{" "}
      {parts.map((part, i) => (
        <span key={part}>
          <mark className={styles.mark} data-lit={i < lit || undefined}>
            {part}
          </mark>
          {i < parts.length - 1 ? ", " : "."}
        </span>
      ))}
    </p>
  )
}

export function Convergence() {
  return (
    <PinnedSequence steps={3} label="Four sources, one arrangement" ground="obsidian" id="finding">
      {(progress) => {
        const call = segment(progress, 0, 0.26)
        const ledger = segment(progress, 0.26, 0.55)
        const corroboration = segment(progress, 0.55, 0.78)
        const closing = segment(progress, 0.8, 1)

        // Each bar rises in turn; the matching quoted amount lights as it does.
        const litAmounts = Math.floor(ledger * (recitedAmounts.length + 1))
        const okonkwo = conflicts[3].okonkwo
        const december = invoiceDescriptions.at(-1)!

        return (
          <div className={styles.wrap}>
            <header className={styles.head}>
              <p className={styles.eyebrow}>The finding</p>
              <h2>Six sources. One arrangement.</h2>
            </header>

            <div className={styles.panels}>
              {/* ---------------------------------------------------- the call */}
              <article className={styles.panel} data-shown={call > 0.1 || undefined}>
                <p className={styles.panelLabel}>
                  <span className={styles.num}>01</span> The call
                </p>
                <p className={styles.meta}>
                  {recording.file} · {recording.date}
                </p>
                <div className={styles.turn}>
                  <span className={styles.at}>00:35</span>
                  <div>
                    <span className={styles.speaker}>Victoria</span>
                    <RecitedTurn lit={litAmounts} />
                  </div>
                </div>
                <div className={styles.turn}>
                  <span className={styles.at}>00:45</span>
                  <div>
                    <span className={styles.speaker}>Victoria</span>
                    <p className={styles.turnText}>that is a line going up.</p>
                  </div>
                </div>
              </article>

              {/* -------------------------------------------------- the ledger */}
              <article className={styles.panel} data-shown={ledger > 0.05 || undefined}>
                <p className={styles.panelLabel}>
                  <span className={styles.num}>02</span> The ledger
                </p>
                <p className={styles.meta}>
                  Extracted independently from 03_bank_statement_nexus.pdf
                </p>
                <div className={styles.chart}>
                  {chartMonths.map((m) => {
                    const index = chartMonths.filter((x) => x.amount > 0).indexOf(m)
                    const risen = m.amount > 0 && index < litAmounts
                    const isDecember = m.month === "Dec"
                    return (
                      <div key={m.month} className={styles.bar}>
                        <span
                          className={styles.barFill}
                          data-december={isDecember || undefined}
                          style={{
                            height: risen ? `${(m.amount / peak) * 100}%` : "0%",
                          }}
                        />
                        <span className={styles.barLabel}>{m.month.slice(0, 1)}</span>
                        {risen && m.amount > 0 ? (
                          <span className={styles.barValue}>{SHORT(m.amount)}</span>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </article>

              {/* ------------------------------------------- the corroboration */}
              <article
                className={styles.panel}
                data-shown={corroboration > 0.05 || undefined}
              >
                <p className={styles.panelLabel}>
                  <span className={styles.num}>03</span> The rest of it
                </p>
                <ul className={styles.corroborations}>
                  <li>
                    <p>
                      The December invoice is described as <strong>“{december.description}”</strong>,
                      filed {december.date}. On the call the day before, Chen says:{" "}
                      <strong>“Year end advisory.”</strong>
                    </p>
                    <p className={styles.cite}>01_whistleblower_report.pdf, p.1</p>
                  </li>
                  <li>
                    <p>
                      {passThrough.proportion} of the money left again within{" "}
                      {passThrough.lagDays}. The suspicious activity report, filed independently,
                      calls it {passThrough.sarFinding}.
                    </p>
                    <p className={styles.cite}>{passThrough.sarSource}</p>
                  </li>
                  <li>
                    <p>“{okonkwo.quote}”</p>
                    <p className={styles.cite}>
                      {okonkwo.file}, p.{okonkwo.page}
                    </p>
                  </li>
                </ul>
              </article>
            </div>

            <p className={styles.closing} data-shown={closing > 0.15 || undefined}>
              No single source establishes this. Each one is unremarkable alone. The model is what
              makes them the same arrangement.
            </p>

            <p className={styles.caption}>Illustrative case data</p>
          </div>
        )
      }}
    </PinnedSequence>
  )
}
