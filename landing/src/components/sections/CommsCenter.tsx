import { commsThread } from "../../data/case"
import styles from "./CommsCenter.module.css"

/**
 * Rebuilt from the app's Cellebrite comms components. No demo UFDR exists and
 * real extractions are live federal matters, so the surface is reconstructed and
 * the thread content is invented. Structure follows CommsThreadView.
 */
export function CommsCenter() {
  // Day boundaries computed up front rather than tracked while mapping —
  // mutating during render is a correctness hazard under concurrent rendering.
  const startsDay = commsThread.entries.map(
    (entry, i) => i === 0 || entry.day !== commsThread.entries[i - 1].day
  )

  return (
    <figure className={styles.frame}>
      <div className={styles.chrome}>
        <div className={styles.device}>
          <p className={styles.deviceName}>{commsThread.device}</p>
          <p className={styles.deviceMeta}>
            {commsThread.handle} · {commsThread.app}
          </p>
        </div>
        <p className={styles.counterparty}>{commsThread.counterparty}</p>
      </div>

      <ol className={styles.thread}>
        {commsThread.entries.map((entry, i) => {
          return (
            <li key={`${entry.day}-${entry.at}-${i}`}>
              {startsDay[i] ? <p className={styles.day}>{entry.day}</p> : null}

              {entry.kind === "call" ? (
                <p className={styles.call}>
                  <span className={styles.callIcon} aria-hidden="true" />
                  Incoming call · {entry.duration}
                  <span className={styles.at}>{entry.at}</span>
                </p>
              ) : (
                <div
                  className={styles.bubbleRow}
                  data-direction={entry.direction}
                >
                  <div className={styles.bubble}>
                    <p>{entry.text}</p>
                    <p className={styles.meta}>
                      <span className={styles.at}>{entry.at}</span>
                      {entry.status ? (
                        <span
                          className={styles.status}
                          data-deleted={
                            entry.status === "Deleted — recovered" ? true : undefined
                          }
                        >
                          {entry.status}
                        </span>
                      ) : null}
                    </p>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ol>

      <figcaption className={styles.caption}>
        Comms Center — illustrative extraction data
      </figcaption>
    </figure>
  )
}
