import { scaleLine } from "../../data/claims"
import styles from "./Hero.module.css"

interface HeroProps {
  onContact: () => void
}

export function Hero({ onContact }: HeroProps) {
  return (
    <section className={styles.hero} id="top">
      <div className={styles.grid} aria-hidden="true" />

      <div className={styles.copy}>
        <p className={styles.eyebrow}>Investigation platform for serious casework</p>
        <h1>Query the whole case.</h1>
        <p className={styles.lede}>
          Loupe resolves phone extractions, documents, financial records and audio into one
          connected model of the case — so a question reaches all of it at once, and every answer
          carries the file, page and passage behind it.
        </p>

        <div className={styles.actions}>
          <button className={styles.primary} type="button" onClick={onContact}>
            Request a walkthrough
          </button>
          <a className={styles.ghost} href="#intake">
            See it work a case
          </a>
        </div>

        <p className={styles.stat}>{scaleLine}</p>
      </div>

      {/* True scale, bleeding off two edges — the point is interface density,
          which a contained thumbnail cannot show. */}
      <div className={styles.shot} aria-hidden="true">
        <img
          src="/product/graph-detail-dark.webp"
          srcSet="/product/graph-detail-dark@1280.webp 1280w, /product/graph-detail-dark.webp 2560w"
          sizes="80vw"
          alt=""
          width={2560}
          height={1440}
          fetchPriority="high"
          decoding="async"
        />
      </div>
      <p className={styles.shotCaption}>Illustrative case data</p>
    </section>
  )
}
