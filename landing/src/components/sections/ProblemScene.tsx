import styles from "./ProblemScene.module.css"

/**
 * One statement, no card grid. The section this replaces was a four-card
 * feature list wearing a problem heading.
 */
export function ProblemScene() {
  return (
    <section className={styles.section} aria-labelledby="problem-heading">
      <div className={styles.wrap}>
        <p className={styles.eyebrow}>The position you are in</p>
        <h2 id="problem-heading" className={styles.statement}>
          You receive the evidence. You didn&rsquo;t collect it and you can&rsquo;t.
        </h2>
        <p className={styles.body}>
          Five phones, hundreds of documents, hours of recorded calls — in formats built by the
          other side, against a court date. And what wins is frequently what is{" "}
          <em>absent</em>: the message that puts someone somewhere else, the date that
          doesn&rsquo;t line up, the deliverable nobody can produce.
        </p>
      </div>
    </section>
  )
}
