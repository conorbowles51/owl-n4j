import { sourcedEntities } from "../../data/case"
import { Reveal } from "../primitives/Reveal"
import styles from "./Sourced.module.css"

/** Native width of the sourced-panel plate (spec §5). Never rendered wider. */
const PLATE_WIDTH = 698

/**
 * Provenance. The one place the page shows — and says — that this is the real
 * product interface. Sits on the same obsidian ground as the Finding above so
 * the payoff and its proof read as a single act.
 */
export function Sourced() {
  // The crop is the details panel for Nexus Trading Ltd; quoting that entity's
  // grounding fact beside it lets the copy and the interface corroborate each
  // other the same way the case sources do.
  const nexus = sourcedEntities.find((e) => e.name === "Nexus Trading Ltd")!

  return (
    <section id="sourced" className={styles.section} aria-labelledby="sourced-heading">
      <div className={styles.wrap}>
        <Reveal>
          <div className={styles.copy}>
            <p className={styles.eyebrow}>Provenance</p>
            <h2 id="sourced-heading" className={styles.heading}>
              Every statement ends in a file and a page.
            </h2>
            <p className={styles.body}>
              A fact exists here only if it has a verbatim quote, a page and a file. Paraphrase
              the model cannot ground is rejected, not published.
            </p>
            <p className={styles.body}>
              And this is the real interface — not a mock-up. The details panel for Nexus Trading
              Ltd, exactly as the product draws it, a red source reference under every statement.
            </p>

            <figure className={styles.fact}>
              <p className={styles.factLabel}>One fact, as the model holds it</p>
              <blockquote className={styles.factQuote}>
                <p>“{nexus.quote}”</p>
              </blockquote>
              <figcaption>
                <span className="receipt receipt-on-dark">
                  {nexus.file}, p.{nexus.page}
                </span>
              </figcaption>
            </figure>
            <p className={styles.factCaption}>Illustrative case data</p>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <figure className={styles.exhibit}>
            <img
              className={styles.plate}
              src="/product/plates/sourced-panel.webp"
              width={PLATE_WIDTH}
              alt="Loupe's details panel for Nexus Trading Ltd: an overview whose statements each carry a red source link naming the file and page behind them."
              loading="lazy"
              decoding="async"
            />
            <figcaption className={styles.caption}>Loupe — actual product interface</figcaption>
          </figure>
        </Reveal>
      </div>
    </section>
  )
}
