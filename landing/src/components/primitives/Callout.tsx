import styles from "./ProductFrame.module.css"

export interface CalloutSpec {
  /** Percentage across the frame, 0–100. */
  x: number
  /** Percentage down the frame, 0–100. */
  y: number
  text: string
  /** Which side the label sits on, when the dot is near an edge. */
  side?: "left" | "right"
}

export function Callout({ x, y, text, side = "right" }: CalloutSpec) {
  return (
    <span
      className={`${styles.callout} ${side === "left" ? styles.calloutLeft : ""}`}
      style={{ left: `${x}%`, top: `${y}%` }}
    >
      <span className={styles.calloutDot} aria-hidden="true" />
      <span className={styles.calloutText}>{text}</span>
    </span>
  )
}
