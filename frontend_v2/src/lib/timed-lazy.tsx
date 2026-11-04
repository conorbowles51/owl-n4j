import { lazy, useEffect, type ComponentType } from "react"
import { chunkArrived, chunkBegan, chunkMounted } from "./page-chunks"

/**
 * React.lazy for route pages, seen by the page timer (lib/page-chunks.ts): the page counts as loading from the
 * moment its code is asked for until it has mounted.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function timedLazy<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  // `preload` starts the download early (main.tsx, for the address a fresh load opens). The page's own render still
  // counts its code as loading from the moment it asks until it mounts; it only finds the code already on its way.
  let early: Promise<{ default: T }> | null = null
  const preload = () => {
    early ??= load()
    early.catch(() => { early = null }) // a failed early download is asked for again by the render
    return early
  }
  const Lazy = lazy(async () => {
    const id = chunkBegan()
    let module: { default: T }
    try {
      module = await (early ?? load())
    } catch (error) {
      chunkArrived(id, true)
      throw error
    }
    const Page = module.default
    let mounted = false
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function TimedPage(props: any) {
      useEffect(() => {
        if (mounted) return
        mounted = true
        chunkMounted(id)
      }, [])
      return <Page {...props} />
    }
    TimedPage.displayName = `Timed(${Page.displayName ?? Page.name ?? "Page"})`
    chunkArrived(id)
    return { default: TimedPage as unknown as T }
  })
  return Object.assign(Lazy, { preload })
}
