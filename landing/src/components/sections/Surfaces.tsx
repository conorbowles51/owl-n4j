import type { CSSProperties } from "react"
import { recording } from "../../data/case"
import { Reveal } from "../primitives/Reveal"
import { CommsCenter } from "./CommsCenter"
import styles from "./Surfaces.module.css"

/**
 * Act II closes on the surfaces. The reader has already seen the finding and
 * its receipts, so each view is presented as an exhibit of the same model
 * rather than a feature: find something in one and it is the same object in
 * every other. Plates are real captures cropped at native width (spec §5);
 * comms is the rebuilt component because no demo UFDR exists.
 *
 * The Financial view is deliberately absent — known product defect (spec §2).
 */

interface PlateExhibit {
  slug: "timeline" | "map" | "audio"
  /**
   * Native plate width in px — the hard cap against upscaling (spec §2).
   * The plates are recut close to display size; each value here is the low
   * end of its recut target so the cap can never exceed the real pixels.
   * Below 768px a `<picture>` swaps in the `-m` variant (640–720 native).
   */
  native: number
  title: string
  body: string
  alt: string
}

const plates: PlateExhibit[] = [
  {
    slug: "timeline",
    native: 950,
    title: "One chronology across every source.",
    body: "Communications, transactions and filings interleave on a single dated spine — notice the citation sitting inside each event, not in a footnote.",
    alt: "The Loupe timeline showing dated event groups, each carrying entity chips and inline source citations.",
  },
  {
    slug: "map",
    native: 900,
    title: "Where it happened, and how sure we are.",
    body: "Geocoded locations with confidence shown honestly — uncertain placements are flagged for review, not quietly pinned.",
    alt: "The Loupe map showing geocoded case locations clustered across Europe, with a confidence legend.",
  },
  {
    slug: "audio",
    native: 1000,
    title: "The recorded call becomes a searchable record.",
    body: "Speakers separated, every turn timestamped and seekable, and the conversation map showing who held the floor across the whole recording.",
    alt: "The Loupe audio viewer showing a speaker-attributed transcript beside a conversation map and transcript search.",
  },
]

export function Surfaces() {
  return (
    <section className={styles.section} id="surfaces" aria-labelledby="surfaces-heading">
      <div className={styles.head}>
        <Reveal>
          <p className={styles.eyebrow}>One structure</p>
          <h2 id="surfaces-heading">The same case, from every angle.</h2>
          <p className={styles.lede}>
            Timeline, map, transcript and phone extractions are not separate tools — they are
            angles on one model. Find something in one and it is the same object in every other.
          </p>
        </Reveal>
      </div>

      <div className={styles.list}>
        {plates.map((plate, i) => (
          <Reveal key={plate.slug}>
            <article
              className={styles.exhibit}
              // Alternation is positional, not structural — the Reveal wrapper
              // sits between .list and the article, so nth-child cannot see it.
              data-flip={i % 2 === 1 ? "" : undefined}
            >
              <div className={styles.copy}>
                <h3>{plate.title}</h3>
                <p>{plate.body}</p>
                {plate.slug === "audio" ? (
                  <p className={styles.fileLine}>
                    <span className="receipt">{recording.file}</span>{" "}
                    <span className={styles.metaSeg}>· {recording.duration}</span>{" "}
                    <span className={styles.metaSeg}>· {recording.turns} turns</span>{" "}
                    <span className={styles.metaSeg}>· {recording.speakers} speakers</span>
                  </p>
                ) : null}
              </div>
              <figure
                className={styles.frame}
                // The frame caps at native width so the plate sits at 1:1;
                // where the container is narrower, the frame crops the right
                // edge rather than downscaling the pixels (finding 1).
                style={{ "--plate-w": `${plate.native}px` } as CSSProperties}
              >
                <div className={styles.plate}>
                  <picture>
                    <source
                      media="(max-width: 767px)"
                      srcSet={`/product/plates/${plate.slug}-m.webp`}
                    />
                    <img
                      src={`/product/plates/${plate.slug}.webp`}
                      alt={plate.alt}
                      loading="lazy"
                      decoding="async"
                    />
                  </picture>
                </div>
                <figcaption className={styles.caption}>Illustrative case data</figcaption>
              </figure>
            </article>
          </Reveal>
        ))}

        <Reveal>
          <article className={`${styles.exhibit} ${styles.commsExhibit}`}>
            <div className={styles.copy}>
              <h3>Phone extractions, kept whole.</h3>
              <p>
                A phone extraction — the UFDR — becomes individual calls, messages and contacts
                with conversations intact. The deleted message is still here, marked recovered
                rather than flattened away.
              </p>
            </div>
            <div className={styles.comms}>
              {/* The window ends of the thread's own accord: the last entry is
                  the recovered deletion, so the badge is on screen by default. */}
              <CommsCenter tail={7} />
            </div>
          </article>
        </Reveal>
      </div>
    </section>
  )
}
