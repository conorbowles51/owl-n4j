import { lazy, useEffect, type ComponentType } from "react"
import { chunkArrived, chunkBegan, chunkMounted } from "./page-chunks"

/**
 * React.lazy for route pages, seen by the page timer (lib/page-chunks.ts): the page counts as loading from the
 * moment its code is asked for until it has mounted.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function timedLazy<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  return lazy(async () => {
    const id = chunkBegan()
    let module: { default: T }
    try {
      module = await load()
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
}
