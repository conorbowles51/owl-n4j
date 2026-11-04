/**
 * Route page chunks (lazy pages in app/routes.tsx) for the page timer (features/financial/lib/page-speed.ts).
 *
 * A lazy page's code arrives before the page asks for its data. Without this, the timer saw "nothing fetching"
 * while the chunk was still loading and recorded the page as on screen too early (measured 4 Nov, signed in:
 * case/map recorded 1,371 ms while its locations request ended at 2,270 ms). A chunk counts from the moment
 * React asks for it until the page it holds has mounted (its own requests have started by then), and only for
 * the address it was asked for: a chunk for an address the person has already left never holds up another page.
 *
 * Opening a page inside the app waits for its chunk before the address changes on screen (router navigations
 * are transitions), so the time a newly mounted page's chunk was asked for is the time the person asked for it.
 */

interface Chunk {
  path: string
  began: number
  resolved: boolean
}

const chunks = new Map<number, Chunk>()
const watchers = new Set<() => void>()
let nextId = 1
let mountedBegan: { at: number; taken: Set<string> } | null = null

function path() {
  return typeof window === "undefined" ? "" : window.location.pathname
}

function changed() {
  for (const watch of [...watchers]) watch()
}

/** A chunk was asked for; returns its id. */
export function chunkBegan(): number {
  const id = nextId++
  chunks.set(id, { path: path(), began: performance.now(), resolved: false })
  return id
}

/** The chunk's code arrived (or failed: `failed`). A chunk for an address already left is dropped. */
export function chunkArrived(id: number, failed = false) {
  const chunk = chunks.get(id)
  if (!chunk) return
  if (failed || chunk.path !== path()) chunks.delete(id)
  else chunk.resolved = true
  changed()
}

/** The page held by the chunk has mounted (its effects, so its requests, have run). */
export function chunkMounted(id: number) {
  const chunk = chunks.get(id)
  if (!chunk) return
  chunks.delete(id)
  mountedBegan = { at: chunk.began, taken: new Set() }
  const mine = mountedBegan
  // Every timer starting in this same commit runs before the next frame; later views are not this page.
  if (typeof requestAnimationFrame !== "undefined") {
    requestAnimationFrame(() => {
      if (mountedBegan === mine) mountedBegan = null
    })
  }
  changed()
}

/** True while a page chunk for the current address is loading or its page has not mounted yet. */
export function pageChunksPending(): boolean {
  const here = path()
  for (const chunk of chunks.values()) if (chunk.path === here) return true
  return false
}

/** When the chunk of a page mounted in this commit was asked for, once per timer channel; null if none. */
export function takeMountedChunkStart(channel: string): number | null {
  if (!mountedBegan || mountedBegan.taken.has(channel)) return null
  mountedBegan.taken.add(channel)
  return mountedBegan.at
}

/** Calls `watch` whenever a chunk begins, arrives or mounts; returns the unsubscribe. */
export function watchPageChunks(watch: () => void): () => void {
  watchers.add(watch)
  return () => {
    watchers.delete(watch)
  }
}

/** Test only: forget every chunk. */
export function resetPageChunks() {
  chunks.clear()
  mountedBegan = null
}
