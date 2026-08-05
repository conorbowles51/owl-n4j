import { useEffect, useState } from "react"

/** Reactive media-query subscription, SSR- and jsdom-safe. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.(query).matches === true
  )

  useEffect(() => {
    const mq = window.matchMedia?.(query)
    if (!mq) return
    const onChange = () => setMatches(mq.matches)
    onChange()
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [query])

  return matches
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)")
}

/**
 * Mirrors the breakpoint at which PinnedSequence.module.css collapses the
 * sticky pin. The two must agree: if the CSS unpins while the JS still drives
 * progress from scroll, every beat renders frozen at its opening frame.
 */
export function useIsNarrow(): boolean {
  return useMediaQuery("(max-width: 767px)")
}
