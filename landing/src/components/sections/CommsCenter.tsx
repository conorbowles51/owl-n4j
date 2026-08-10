import { commsThread } from "../../data/case"
import styles from "./CommsCenter.module.css"

interface CommsCenterProps {
  /**
   * Show only the last `tail` entries, with a faded indicator standing in
   * for the earlier ones. The thread data is untouched — this is a viewport
   * onto the end of the conversation, which is where the recovered deletion
   * lives, so the exhibit ends on whole bubbles with the badge on screen.
   */
  tail?: number
}

/**
 * Rebuilt from the app's Cellebrite comms components. No demo UFDR exists and
 * real extractions are live federal matters, so the surface is reconstructed and
 * the thread content is invented. Structure follows CommsThreadView.
 */
export function CommsCenter({ tail }: CommsCenterProps) {
  const entries =
    tail === undefined ? [...commsThread.entries] : commsThread.entries.slice(-tail)
  const elided = commsThread.entries.length - entries.length

  // Day boundaries computed up front rather than tracked while mapping —
  // mutating during render is a correctness hazard under concurrent rendering.
  const startsDay = entries.map((entry, i) => i === 0 || entry.day !== entries[i - 1].day)

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

      {elided > 0 ? <p className={styles.earlier}>{elided} earlier messages</p> : null}

      <ol className={styles.thread}>
        {entries.map((entry, i) => {
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
