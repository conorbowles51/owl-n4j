import {
  entityColours,
  graphCounts,
  pipelineStages,
  sourcedEntities,
} from "../../data/case"
import { segment } from "../../lib/useScrollProgress"
import { PinnedSequence } from "../primitives/PinnedSequence"
import styles from "./ModelResolve.module.css"

export function ModelResolve() {
  return (
    <PinnedSequence steps={2} label="Evidence becoming a model" ground="obsidian">
      {(progress) => {
        const staged = segment(progress, 0.05, 0.75)
        const activeStage = Math.min(
          pipelineStages.length - 1,
          Math.floor(staged * pipelineStages.length)
        )
        const emitting = segment(progress, 0.3, 0.85)
        const closing = segment(progress, 0.85, 1)
        const counted = Math.round(segment(progress, 0.3, 0.9) * graphCounts.all.nodes)

        return (
          <div className={styles.wrap}>
            <header className={styles.head}>
              <p className={styles.eyebrow}>Resolution</p>
              <h2>Every fact arrives holding its source.</h2>
            </header>

            <div className={styles.grid}>
              <ol className={styles.stages}>
                {pipelineStages.map((stage, i) => (
                  <li
                    key={stage}
                    data-state={
                      i < activeStage ? "done" : i === activeStage ? "active" : undefined
                    }
                  >
                    <span className={styles.stageIndex}>{String(i + 1).padStart(2, "0")}</span>
                    <span className={styles.stageName}>{stage}</span>
                  </li>
                ))}
              </ol>

              <div className={styles.field}>
                <p className={styles.counter}>
                  <span>{counted}</span> entities resolved
                </p>
                <ul className={styles.chips}>
                  {sourcedEntities.map((entity, i) => {
                    const shown = emitting > i / sourcedEntities.length
                    return (
                      <li key={entity.name} data-shown={shown || undefined}>
                        <p className={styles.chipHead}>
                          <span
                            className={styles.dot}
                            style={{ background: entityColours[entity.type] }}
                            aria-hidden="true"
                          />
                          <strong>{entity.name}</strong>
                          <em>{entity.type}</em>
                        </p>
                        <blockquote className={styles.quote}>“{entity.quote}”</blockquote>
                        <p className={styles.cite}>
                          {entity.file}, p.{entity.page}
                        </p>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </div>

            <p className={styles.rule} data-shown={closing > 0.15 || undefined}>
              A fact exists here only if it has a verbatim quote, a page and a file. Paraphrase
              the model cannot ground is rejected, not published.
            </p>
          </div>
        )
      }}
    </PinnedSequence>
  )
}
