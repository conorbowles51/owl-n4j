import { useEffect, useRef, useState, type ReactNode } from "react"
import { usePrefersReducedMotion } from "../../lib/useMediaQuery"
import styles from "./Reveal.module.css"

interface RevealProps {
  /** Stagger, in ms. */
  delay?: number
  children: ReactNode
}

/**
 * Fades content up once as it enters the viewport. Under reduced motion — or in
 * environments without IntersectionObserver — content is simply visible.
 */
export function Reveal({ delay = 0, children }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = usePrefersReducedMotion()
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (reduced || shown) return
    const el = ref.current
    if (!el || typeof IntersectionObserver === "undefined") {
      setShown(true)
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShown(true)
          io.disconnect()
        }
      },
      // Shallow trigger: content should never be visibly mid-fade once it is
      // meaningfully inside the viewport — reviewers read late fades as broken.
      { rootMargin: "0px 0px -6% 0px" }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [reduced, shown])

  return (
    <div
      ref={ref}
      className={reduced || shown ? `${styles.reveal} ${styles.shown}` : styles.reveal}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  )
}
