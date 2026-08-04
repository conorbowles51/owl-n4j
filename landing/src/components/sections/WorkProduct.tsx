import { agentCaveat } from "../../data/case"
import { ProductFrame } from "../primitives/ProductFrame"
import styles from "./WorkProduct.module.css"

export function WorkProduct() {
  return (
    <section className={styles.section} aria-labelledby="work-product-heading">
      <div className={styles.wrap}>
        <div className={styles.head}>
          <p className={styles.eyebrow}>Work product</p>
          <h2 id="work-product-heading">What you walk out with.</h2>
          <p className={styles.lede}>
            A report scoped to what you asked for, every assertion citing the document behind it,
            exportable and still attached to the case it came from.
          </p>
        </div>

        <ProductFrame
          slug="agent-report"
          alt="A Loupe report draft with scoped sections, an executive assessment, inline source citations, and PDF and Word export."
          theme="light"
          callouts={[{ x: 46, y: 62, text: "Citation after every assertion" }]}
        />

        <blockquote className={styles.caveat}>
          <p>{agentCaveat}</p>
          <cite>From the report&rsquo;s own &ldquo;evidentiary caveats and open questions&rdquo;</cite>
        </blockquote>
      </div>
    </section>
  )
}
