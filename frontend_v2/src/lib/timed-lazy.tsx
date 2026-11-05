import { lazy, useEffect, type ComponentType, type LazyExoticComponent } from "react"
import { chunkArrived, chunkBegan, chunkMounted } from "./page-chunks"

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type TimedLazyPage<T extends ComponentType<any>> = LazyExoticComponent<T> & {
  preload: () => void
}

/**
 * React.lazy for route pages, seen by the page timer (lib/page-chunks.ts): the page counts as loading from the
 * moment React asks for its code until it has mounted. `preload` starts the same download when the person points at
 * a link to the page (lib/route-preload.ts); React then reuses it, so the code is fetched once, and the timer is not
 * told, so a page the person never opens never holds up the one on screen.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function timedLazy<T extends ComponentType<any>>(load: () => Promise<{ default: T }>): TimedLazyPage<T> {
  let download: Promise<{ default: T }> | null = null

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
    const id = chunkBegan()
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

  Page.preload = () => {
    void fetchCode().catch(() => {})
  }
  return Page
}
