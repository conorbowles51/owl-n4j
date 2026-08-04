import { agentScopeNote, agentTrail, clarification, conflicts } from "../../data/case"
import { segment } from "../../lib/useScrollProgress"
import { PinnedSequence } from "../primitives/PinnedSequence"
import styles from "./AgentExchange.module.css"

const QUESTION =
  "Compare what Marcus Chen and David Okonkwo each said about the Nexus Trading vendor relationship."

export function AgentExchange() {
  return (
    <PinnedSequence steps={2} label="Asking the agent" ground="paper" id="agent">
      {(progress) => {
        const typing = segment(progress, 0, 0.18)
        const asking = segment(progress, 0.2, 0.38)
        const building = segment(progress, 0.42, 0.78)
        const scope = segment(progress, 0.8, 1)

        const typed = QUESTION.slice(0, Math.round(typing * QUESTION.length))

        return (
          <div className={styles.wrap}>
            <header className={styles.head}>
              <p className={styles.eyebrow}>The agent</p>
              <h2>Ask for work, not for prose.</h2>
            </header>

            <div className={styles.split}>
              {/* ----------------------------------------------- conversation */}
              <div className={styles.thread}>
                <p className={styles.fromUser}>
                  {typed}
                  {typing < 1 ? <span className={styles.caret} aria-hidden="true" /> : null}
                </p>

                <div className={styles.fromAgent} data-shown={asking > 0.1 || undefined}>
                  <p className={styles.ask}>{clarification.ask}</p>
                  <ul className={styles.options}>
                    {clarification.options.map((option) => (
                      <li
                        key={option}
                        data-chosen={
                          asking > 0.75 && option === clarification.chosen ? true : undefined
                        }
                      >
                        {option}
                      </li>
                    ))}
                  </ul>
                  <p className={styles.asks}>It asks. It does not guess.</p>
                </div>

                <div className={styles.trail} data-shown={building > 0.5 || undefined}>
                  Investigation trail — {agentTrail.steps} steps · {agentTrail.seconds}s
                </div>
              </div>

              {/* -------------------------------------------------- artifact */}
              <div className={styles.artifact} data-shown={building > 0.05 || undefined}>
                <p className={styles.artifactHead}>
                  Conflicts in Chen and Okonkwo interviews — Nexus Trading
                </p>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th scope="col">Conflict point</th>
                      <th scope="col">Chen</th>
                      <th scope="col">Okonkwo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conflicts.map((conflict, i) => (
                      <tr
                        key={conflict.point}
                        data-shown={building > (i + 1) / (conflicts.length + 1) || undefined}
                      >
                        <th scope="row">{conflict.point}</th>
                        <td>
                          <span className={styles.quote}>“{conflict.chen.quote}”</span>
                          <span className={styles.cite}>
                            {conflict.chen.file}, p.{conflict.chen.page}
                          </span>
                        </td>
                        <td>
                          <span className={styles.quote}>“{conflict.okonkwo.quote}”</span>
                          <span className={styles.cite}>
                            {conflict.okonkwo.file}, p.{conflict.okonkwo.page}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <blockquote className={styles.scope} data-shown={scope > 0.15 || undefined}>
              <p>{agentScopeNote}</p>
              <cite>The agent, stating what it left out</cite>
            </blockquote>

            <p className={styles.caption}>Illustrative case data</p>
          </div>
        )
      }}
    </PinnedSequence>
  )
}
