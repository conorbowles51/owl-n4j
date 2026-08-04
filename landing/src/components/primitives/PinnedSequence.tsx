import type { ReactNode } from "react"
import { usePrefersReducedMotion } from "../../lib/usePrefersReducedMotion"
import { useScrollProgress } from "../../lib/useScrollProgress"
import styles from "./PinnedSequence.module.css"

interface PinnedSequenceProps {
  /** How many viewport-heights of scroll the sequence occupies beyond the first. */
  steps: number
  /** Accessible name for the region. */
  label: string
  /** Anchor id, for nav links. */
  id?: string
  /** Render the completed state immediately, skipping scroll choreography. */
  forceComplete?: boolean
  children: (progress: number) => ReactNode
}

export function PinnedSequence({
  steps,
  label,
  id,
  forceComplete = false,
  children,
}: PinnedSequenceProps) {
  const { ref, progress } = useScrollProgress<HTMLElement>()
  const reduced = usePrefersReducedMotion()
  const complete = forceComplete || reduced

  return (
    <section
      ref={ref}
      id={id}
      aria-label={label}
      className={styles.track}
      style={{ minHeight: complete ? "auto" : `${(steps + 1) * 100}svh` }}
    >
      <div className={complete ? `${styles.pin} ${styles.static}` : styles.pin}>
        {children(complete ? 1 : progress)}
      </div>
    </section>
  )
}
