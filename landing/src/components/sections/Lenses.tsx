import { ProductFrame } from "../primitives/ProductFrame"
import { CommsCenter } from "./CommsCenter"
import styles from "./Lenses.module.css"

/**
 * Not a tab strip. Each surface gets full width and a caption that says what
 * the reader is looking at, with callouts pointing at the one thing that matters.
 *
 * Table and Reports are deliberately absent: Table's amount, date, file and
 * location columns are empty across every row, and Reports is a work in progress.
 */
const lenses = [
  {
    slug: "graph-detail",
    title: "Every claim keeps its route back.",
    body: "Select any object and the summary behind it cites the file and page each statement came from. Nothing in the panel is the model's own words about the evidence — it is the evidence, quoted.",
    alt: "The Loupe graph view with an organisation selected. Its detail panel shows a summary in which every statement links to the source file and page it came from.",
    callouts: [{ x: 74, y: 30, text: "Every statement ends in the file and page it came from" }],
  },
  {
    slug: "audio-transcript",
    title: "Recorded calls become searchable record.",
    body: "Speakers separated, every turn timestamped and seekable, the whole transcript searchable in place. The conversation map shows who held the floor across the recording.",
    alt: "The Loupe audio evidence viewer showing a speaker-attributed transcript beside a two-lane conversation map.",
    callouts: [{ x: 22, y: 26, text: "Speaker turns across the whole recording" }],
  },
  {
    slug: "timeline",
    title: "One chronology across every source.",
    body: "Communications, transactions, events and documents on a single timeline — each carrying the entities it involves and the file it came from.",
    alt: "The Loupe timeline showing dated event groups, each with entity chips and inline source citations.",
    callouts: [{ x: 60, y: 47, text: "Source citation inside the event itself" }],
  },
  {
    slug: "financial",
    title: "Money, with its provenance attached.",
    body: "Counterparties resolved to who they actually are, and every row badged with the document it was read from.",
    alt: "The Loupe financial view listing transactions with sender, receiver, amount and a provenance column.",
    callouts: [{ x: 82, y: 34, text: "Provenance badge on every transaction" }],
  },
  {
    slug: "map",
    title: "Where it happened, and how sure we are.",
    body: "Geocoded locations with confidence shown honestly — including the ones flagged for review rather than quietly placed.",
    alt: "The Loupe map showing geocoded case locations across Europe and the Caribbean with a confidence legend.",
    callouts: [],
  },
]

export function Lenses() {
  return (
    <section className={styles.section} id="lenses" aria-labelledby="lenses-heading">
      <div className={styles.head}>
        <p className={styles.eyebrow}>Perspectives</p>
        <h2 id="lenses-heading">One case, worked from every angle.</h2>
        <p className={styles.lede}>
          Not separate tools. Perspectives on one structure — which is why a finding in one is the
          same object in another.
        </p>
      </div>

      <div className={styles.list}>
        {lenses.map((lens) => (
          <article key={lens.slug} className={styles.lens}>
            <div className={styles.copy}>
              <h3>{lens.title}</h3>
              <p>{lens.body}</p>
            </div>
            <ProductFrame
              slug={lens.slug}
              alt={lens.alt}
              callouts={lens.callouts}
              theme="light"
              bleed
            />
          </article>
        ))}

        <article className={styles.lens}>
          <div className={styles.copy}>
            <h3>Phone extractions, kept whole.</h3>
            <p>
              A UFDR becomes individual calls, messages, contacts and locations — each queryable,
              conversations intact, and the extraction&rsquo;s own metadata preserved rather than
              flattened away.
            </p>
          </div>
          <div className={styles.commsHolder}>
            <CommsCenter />
          </div>
        </article>
      </div>
    </section>
  )
}
