import { lazy, useEffect, type ComponentType, type LazyExoticComponent } from "react"
import { chunkArrived, chunkBegan, chunkMounted } from "./page-chunks"

/**
 * How a page's code is asked for before React renders it:
 * - "start": the page at the address the app opened on (lib/route-preload.ts). The page timer counts it as
 *   loading from now, exactly as if React had asked for it, because this is the page being opened.
 * - "intent": the person is pointing at a link to it. Only the download starts; the timer is not told,
 *   so a page the person never opens never holds up the one on screen.
 */
export type PreloadReason = "start" | "intent"

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type TimedLazyPage<T extends ComponentType<any>> = LazyExoticComponent<T> & {
  preload: (reason: PreloadReason) => void
}

/**
 * React.lazy for route pages, seen by the page timer (lib/page-chunks.ts): the page counts as loading from the
 * moment its code is asked for until it has mounted. `preload` starts the same download earlier; React then
 * reuses it, so the code is fetched once.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function timedLazy<T extends ComponentType<any>>(load: () => Promise<{ default: T }>): TimedLazyPage<T> {
  let download: Promise<{ default: T }> | null = null
  let startedId: number | null = null
  let asked = false

  const fetchCode = () => {
    if (!download) {
      download = load()
      // A failed download is asked for again next time (React shows the error panel's retry).
      download.catch(() => {
        download = null
      })
    }
    return download
  }

  const Page = lazy(async () => {
    asked = true
    const id = startedId ?? chunkBegan()
    startedId = null
    let module: { default: T }
    try {
      module = await fetchCode()
    } catch (error) {
      chunkArrived(id, true)
      throw error
    }
    const Inner = module.default
    let mounted = false
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function TimedPage(props: any) {
      useEffect(() => {
        if (mounted) return
        mounted = true
        chunkMounted(id)
      }, [])
      return <Inner {...props} />
    }
    TimedPage.displayName = `Timed(${Inner.displayName ?? Inner.name ?? "Page"})`
    chunkArrived(id)
    return { default: TimedPage as unknown as T }
  }) as TimedLazyPage<T>

  Page.preload = (reason) => {
    if (reason === "start" && !asked && startedId === null) startedId = chunkBegan()
    void fetchCode().catch(() => {})
  }
  return Page
}
