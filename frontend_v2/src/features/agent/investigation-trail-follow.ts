import { useCallback, useEffect, useRef } from "react"

/**
 * Each step's detail line, or null where an earlier step already showed the same line. Every phone step said
 * "I'm reading this case's phone records in full, citing each record." (coordinator check, 12 Nov): it is shown once.
 */
export function firstShownDetails(details: Array<string | null | undefined>): Array<string | null> {
  const seen = new Set<string>()
  return details.map((detail) => {
    const text = (detail ?? "").trim()
    if (!text || seen.has(text)) return null
    seen.add(text)
    return detail ?? null
  })
}

function scrollParent(element: HTMLElement): HTMLElement | null {
  let node = element.parentElement
  while (node) {
    const overflow = getComputedStyle(node).overflowY
    if ((overflow === "auto" || overflow === "scroll") && node.scrollHeight > node.clientHeight) return node
    node = node.parentElement
  }
  return null
}

function inView(element: HTMLElement): boolean {
  const parent = scrollParent(element)
  const rect = element.getBoundingClientRect()
  const top = parent ? parent.getBoundingClientRect().top : 0
  const bottom = parent ? parent.getBoundingClientRect().bottom : window.innerHeight
  return rect.top < bottom && rect.bottom > top
}

/**
 * While a run is live, a new step is scrolled into view when the step before it was in view: the reader is
 * following the trail. A reader who scrolled away keeps their place. Returns the ref for the newest step.
 */
export function useFollowNewestStep(count: number, live: boolean) {
  const newest = useRef<HTMLElement | null>(null)
  const previous = useRef<HTMLElement | null>(null)

  // After a new step renders, the step that was newest is still on the page: if it was in view, follow.
  useEffect(() => {
    const element = newest.current
    if (!element) return
    if (live && previous.current && previous.current !== element && previous.current.isConnected
        && inView(previous.current)) {
      element.scrollIntoView?.({ block: "nearest", behavior: "smooth" })
    }
    previous.current = element
  }, [count, live])

  return useCallback((element: HTMLElement | null) => {
    if (element) newest.current = element
  }, [])
}
