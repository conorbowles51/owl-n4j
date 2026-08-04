import { evidenceFiles, evidenceTotalEntities, folders } from "../../data/case"
import { segment } from "../../lib/useScrollProgress"
import { PinnedSequence } from "../primitives/PinnedSequence"
import styles from "./IntakeStream.module.css"

/** The machinery each format goes through. Named, not gestured at. */
const machinery = [
  ["Phone extractions", "UFDR parsed to individual calls, messages, contacts and locations"],
  ["Scanned discovery", "OCR'd page by page, native text layers left alone"],
  ["Recorded calls", "Transcribed and separated by speaker"],
  ["Statements and ledgers", "Tables kept as tables, not flattened into prose"],
]

export function IntakeStream() {
  return (
    <PinnedSequence steps={2} label="Evidence intake" id="intake">
      {(progress) => {
        const arriving = segment(progress, 0, 0.6)
        const typing = segment(progress, 0.3, 0.75)
        const caption = segment(progress, 0.75, 1)

        return (
          <div className={styles.wrap}>
            <header className={styles.head}>
              <p className={styles.eyebrow}>Intake</p>
              <h2>Everything arrives in the format the other side chose.</h2>
            </header>

            <div className={styles.explorer}>
              <aside className={styles.rail} aria-hidden="true">
                <p className={styles.railLabel}>Folders</p>
                <ul>
                  {folders.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </aside>

              <div className={styles.table}>
                <div className={styles.thead} aria-hidden="true">
                  <span>Name</span>
                  <span>Type</span>
                  <span>Size</span>
                  <span>Entities</span>
                </div>
                <ul className={styles.rows}>
                  {evidenceFiles.map((file, i) => {
                    const threshold = i / evidenceFiles.length
                    const shown = arriving > threshold
                    const typed = typing > threshold
                    return (
                      <li
                        key={file.name}
                        className={styles.row}
                        data-shown={shown || undefined}
                      >
                        <span className={styles.name}>{file.name}</span>
                        <span
                          className={styles.kind}
                          data-kind={typed ? file.kind : undefined}
                        >
                          {typed ? file.kind : ""}
                        </span>
                        <span className={styles.size}>{file.size}</span>
                        <span className={styles.entities}>
                          {typed ? `${file.entities} / ${evidenceTotalEntities}` : ""}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </div>

            <div className={styles.caption} data-shown={caption > 0.05 || undefined}>
              <ul className={styles.machinery}>
                {machinery.map(([what, how]) => (
                  <li key={what}>
                    <strong>{what}</strong>
                    <span>{how}</span>
                  </li>
                ))}
              </ul>
              <p className={styles.window}>
                A few hundred documents takes twelve to twenty-four hours. It runs unattended
                overnight.
              </p>
            </div>
          </div>
        )
      }}
    </PinnedSequence>
  )
}
