import {
  chartMonths,
  chartSource,
  conflicts,
  invoiceDescriptions,
  passThrough,
  recitedAmounts,
  recording,
  transcript,
} from "../../data/case"
import { Reveal } from "../primitives/Reveal"
import styles from "./Finding.module.css"

const EUR = (n: number) => `€${n.toLocaleString("en-GB")}`

/** Filed against each payment. Source noted in case.ts beside the data. */
const INVOICE_SOURCE = "01_whistleblower_report.pdf, p.1"

// The 00:35 turn carries the recitation. The fragments after the dash are the
// five amounts in the order Blackwood says them — which is also the order they
// appear on the bank statement and on the invoice schedule. That coincidence
// of order is the finding, so the spine derives everything from the data
// rather than restating it.
const recitedTurn = transcript.find((t) => t.at === "00:35")!
const [intent, recitation] = recitedTurn.text.split("—").map((s) => s.trim())
const spokenFragments = recitation
  .replace(/\.$/, "")
  .split(",")
  .map((s) => s.trim())

const traces = recitedAmounts.map((amount, i) => ({
  amount,
  spoken: spokenFragments[i],
  banked: chartMonths.find((m) => m.amount === amount)!,
  invoiced: invoiceDescriptions.find((d) => d.amount === amount)!,
}))

// The sixth payment: the phrase spoken on the 19th, filed on the 20th.
const yearEndSpoken = transcript.find((t) => t.at === "00:21")!
const yearEndInvoice = invoiceDescriptions.find(
  (d) => d.description === "Year-End Advisory Services"
)!

// The release promise: Chen names David on the call; both interviews describe
// the arrangement from opposite ends.
const releaseTurn = transcript.find((t) => t.at === "00:23")!
const promise = conflicts[3]

const sarRate = passThrough.sarFinding.match(/^\d+%/)![0]

/**
 * One receipt, wrap-safe. The filename and the ", p.N" / ", 00:35" reference
 * are each held in a nowrap span; the <wbr> between them is the only break
 * opportunity, switched on only below 480px where receipts are allowed to
 * wrap at all (Finding.module.css). A wrapped receipt therefore breaks
 * between file and reference — never inside the reference.
 */
function Receipt({ source }: { source: string }) {
  const split = source.lastIndexOf(", ")
  if (split < 0) return <span className="receipt receipt-on-dark">{source}</span>
  return (
    <span className="receipt receipt-on-dark">
      <span className={styles.receiptPart}>{source.slice(0, split)}</span>
      <wbr className={styles.receiptBreak} />
      <span className={styles.receiptPart}>{source.slice(split)}</span>
    </span>
  )
}

/**
 * The climax. The five recited amounts as a ledger spine, each traced to the
 * call, the bank statement and the invoice schedule; then the two moments the
 * spine cannot carry alone. In-flow — the reader scrolls a ledger, not a
 * slideshow — and every connection is on the page without interaction.
 * Spec §4.6.
 */
export function Finding() {
  return (
    <section id="finding" className={styles.section}>
      <div className={styles.inner}>
        <Reveal>
          <header className={styles.head}>
            <p className={styles.eyebrow}>The finding</p>
            <h2 className={styles.title}>Five amounts. Six sources. One story.</h2>
            <p className={styles.lede}>
              Thirty-five seconds into the recorded call, Victoria Blackwood says
              “{intent}” and recites five figures. Loupe had already placed every
              one of them, twice, before anyone pressed play.
            </p>
          </header>
        </Reveal>

        {/* ------------------------------------------------------- the spine */}
        <div className={styles.spine}>
          <Reveal>
            <p className={styles.spineNote}>
              Five figures · recited in the order they landed and were invoiced
            </p>
          </Reveal>
          {traces.map((t, i) => (
            <Reveal key={t.amount} delay={i * 60}>
              <article className={styles.band}>
                <div className={styles.amountCell}>
                  <span className={styles.index}>{String(i + 1).padStart(2, "0")}</span>
                  <p className={styles.amount}>{EUR(t.amount)}</p>
                </div>
                <ul className={styles.rows}>
                  <li className={styles.row}>
                    <span className={styles.tag}>Spoken</span>
                    <p className={styles.fact}>
                      “<strong>{t.spoken}</strong>”
                    </p>
                    <Receipt source={`${recording.file}, 00:35`} />
                  </li>
                  <li className={styles.row}>
                    <span className={styles.tag}>Banked</span>
                    <p className={styles.fact}>
                      Incoming payment to Nexus Trading · {t.banked.month} 2023
                    </p>
                    <Receipt source={chartSource} />
                  </li>
                  <li className={styles.row}>
                    <span className={styles.tag}>Invoiced</span>
                    <p className={styles.fact}>
                      “{t.invoiced.description}” · filed {t.invoiced.date}
                    </p>
                    <Receipt source={INVOICE_SOURCE} />
                  </li>
                </ul>
              </article>
            </Reveal>
          ))}
        </div>

        {/* ----------------------------------------------------- the moments */}
        <div className={styles.proof}>
          <div className={styles.moments}>
            <Reveal>
              <article className={styles.moment}>
                <p className={styles.kicker}>The phrase</p>
                <h3 className={styles.momentTitle}>
                  Spoken on the 19th. Filed on the 20th.
                </h3>
                <div className={styles.phrase}>
                  <p className={styles.phraseMeta}>
                    Marcus Chen, on the call · {recording.date} · 00:21
                  </p>
                  <p className={styles.phraseText}>
                    <mark>“{yearEndSpoken.text}”</mark>
                  </p>
                  <Receipt source={`${recording.file}, 00:21`} />
                </div>
                <p className={styles.phraseJoin} aria-hidden="true">
                  ↓
                </p>
                <div className={styles.phrase}>
                  <p className={styles.phraseMeta}>
                    Invoice for {EUR(yearEndInvoice.amount)} · filed{" "}
                    {yearEndInvoice.date}
                  </p>
                  <p className={styles.phraseText}>
                    <mark>“{yearEndInvoice.description}”</mark>
                  </p>
                  <Receipt source={INVOICE_SOURCE} />
                </div>
              </article>
            </Reveal>

            <Reveal delay={90}>
              <article className={styles.moment}>
                <p className={styles.kicker}>The echo</p>
                <h3 className={styles.momentTitle}>Counted twice, independently.</h3>
                <div className={styles.echoFigures}>
                  <div className={styles.echoCol}>
                    <p className={styles.echoValue}>{passThrough.proportion}</p>
                    <p className={styles.echoLabel}>
                      {EUR(passThrough.onward)} of {EUR(passThrough.inbound)} out
                      again within {passThrough.lagDays} — measured across the
                      model
                    </p>
                  </div>
                  <div className={styles.echoCol}>
                    <p className={styles.echoValue}>{sarRate}</p>
                    <p className={styles.echoLabel}>
                      the rate in the bank’s own suspicious activity report, filed
                      independently
                    </p>
                  </div>
                </div>
                <p className={styles.echoQuote}>“{passThrough.sarFinding}”</p>
                <Receipt source={passThrough.sarSource} />
              </article>
            </Reveal>
          </div>

          <Reveal>
            <article className={`${styles.moment} ${styles.momentWide}`}>
              <p className={styles.kicker}>The corroboration</p>
              <h3 className={styles.momentTitle}>The promise behind the release.</h3>
              <p className={styles.momentLede}>
                On the call, the payment needs a David to release it. Interviewed,
                David Okonkwo describes what he was offered for helping; Chen
                describes a vendor relationship.
              </p>
              <div className={styles.quotes}>
                <div className={styles.quoteBlock}>
                  <p className={styles.quoteMeta}>Marcus Chen · on the call, 00:23</p>
                  <p className={styles.quoteText}>“{releaseTurn.text}”</p>
                  <Receipt source={`${recording.file}, 00:23`} />
                </div>
                <div className={styles.quoteBlock}>
                  <p className={styles.quoteMeta}>David Okonkwo · interviewed</p>
                  <p className={styles.quoteText}>“{promise.okonkwo.quote}”</p>
                  <Receipt
                    source={`${promise.okonkwo.file}, p.${promise.okonkwo.page}`}
                  />
                </div>
                <div className={styles.quoteBlock}>
                  <p className={styles.quoteMeta}>Marcus Chen · interviewed</p>
                  <p className={styles.quoteText}>“{promise.chen.quote}”</p>
                  <Receipt
                    source={`${promise.chen.file}, p.${promise.chen.page}`}
                  />
                </div>
              </div>
            </article>
          </Reveal>
        </div>

        {/* ----------------------------------------------------- the closing */}
        <Reveal>
          <div className={styles.close}>
            <p className={styles.closing}>
              No single file contains this. The model does.
            </p>
            <p className={styles.caption}>Illustrative case data</p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
