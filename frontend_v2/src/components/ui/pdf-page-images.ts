import { evidenceAPI } from "@/features/evidence/api"

/**
 * Authenticated PDF page images shared by every viewer in the tab.
 *
 * Measured 2026-10-30: opening a PDF started about 15 page renders within 0.8 s, page 1 was fetched twice (the
 * first-page view and then the list's own page-1 row), and scrolling back fetched a page again. Here each page
 * image (file, page, width, signed-in token) is fetched once and kept for the tab, a request for a page already on
 * its way joins it, and at most MAX_IN_FLIGHT page requests run at once; the rest wait their turn and leave the
 * queue when nobody wants them any more. A failed page is not kept, so Retry asks the server again.
 *
 * The server answers with an ETag and `private, no-cache`, so an image this store no longer holds is still a 304
 * from the browser's own cache after the server's access check.
 */
export const MAX_IN_FLIGHT = 3
const MAX_KEPT_BYTES = 80 * 1024 * 1024
const MAX_PAGE_BYTES = 20 * 1024 * 1024

export interface PageImage {
  blob: Blob
  /** The document's page count, when the server sent it. */
  pageCount: number | null
  /** Pixel size of the rendered page, when the server sent it. */
  size: { width: number; height: number } | null
}

interface Pending {
  promise: Promise<PageImage>
  controller: AbortController
  wanted: number
  started: boolean
  start: () => void
}

const kept = new Map<string, PageImage>()
let keptBytes = 0
const pending = new Map<string, Pending>()
const queue: string[] = []
let inFlight = 0

function keyFor(evidenceId: string, page: number, width: number | undefined, token: string | null) {
  return JSON.stringify([token, evidenceId, page, width ?? null])
}

function keep(key: string, image: PageImage) {
  const previous = kept.get(key)
  if (previous) keptBytes -= previous.blob.size
  kept.delete(key)
  kept.set(key, image)
  keptBytes += image.blob.size
  for (const [oldest, value] of kept) {
    if (keptBytes <= MAX_KEPT_BYTES || oldest === key) break
    kept.delete(oldest)
    keptBytes -= value.blob.size
  }
}

function pump() {
  while (inFlight < MAX_IN_FLIGHT && queue.length) {
    const key = queue.shift()!
    const entry = pending.get(key)
    if (entry && !entry.started) entry.start()
  }
}

function parseSize(value: string | null) {
  const match = value?.match(/^(\d+)x(\d+)$/)
  if (!match) return null
  const width = Number(match[1])
  const height = Number(match[2])
  return width > 0 && height > 0 ? { width, height } : null
}

async function fetchPage(
  evidenceId: string,
  page: number,
  width: number | undefined,
  token: string | null,
  signal: AbortSignal
): Promise<PageImage> {
  const response = await fetch(evidenceAPI.getPageImageUrl(evidenceId, page, width), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
    signal,
  })
  if (!response.ok)
    throw new Error(
      response.status === 401 || response.status === 403
        ? "You do not currently have access to this file. Sign in again or check your case access."
        : `Page ${page} could not be loaded. Try again or open the original file in a new tab.`
    )
  if (!response.headers.get("content-type")?.startsWith("image/png"))
    throw new Error("The server did not return a PDF page. Try again.")
  const count = Number(response.headers.get("X-PDF-Page-Count"))
  const size = parseSize(response.headers.get("X-PDF-Page-Image-Size"))
  const blob = await response.blob()
  if (blob.size > MAX_PAGE_BYTES)
    throw new Error("This page is too large to display. Open the original file in a new tab.")
  return {
    blob,
    pageCount: Number.isSafeInteger(count) && count >= page ? count : null,
    size,
  }
}

function abortError() {
  return new DOMException("The page is no longer wanted.", "AbortError")
}

/**
 * The page image, from this tab's store, a request already on its way, or a new request in turn. `signal` is this
 * caller's interest: when every caller of a page has aborted, its request is dropped from the queue or aborted.
 */
export function loadPageImage(
  evidenceId: string,
  page: number,
  options: { width?: number; token: string | null; signal: AbortSignal }
): Promise<PageImage> {
  const { width, token, signal } = options
  if (signal.aborted) return Promise.reject(abortError())
  const key = keyFor(evidenceId, page, width, token)
  const ready = kept.get(key)
  if (ready) {
    kept.delete(key)
    kept.set(key, ready) // most recently used
    return Promise.resolve(ready)
  }
  let entry = pending.get(key)
  if (!entry) {
    const controller = new AbortController()
    let start!: () => void
    const begun = new Promise<void>((resolve) => {
      start = () => {
        created.started = true
        inFlight += 1
        resolve()
      }
    })
    const promise = begun
      .then(() => fetchPage(evidenceId, page, width, token, controller.signal))
      .then((image) => {
        keep(key, image)
        return image
      })
      .finally(() => {
        pending.delete(key)
        inFlight -= 1
        pump()
      })
    const created: Pending = { promise, controller, wanted: 0, started: false, start }
    entry = created
    pending.set(key, created)
    queue.push(key)
    promise.catch(() => undefined) // a caller who left must not see an unhandled rejection
    pump()
  }
  const current = entry
  current.wanted += 1
  return new Promise<PageImage>((resolve, reject) => {
    const leave = () => {
      current.wanted -= 1
      if (current.wanted === 0) {
        if (current.started) current.controller.abort()
        else {
          const index = queue.indexOf(key)
          if (index >= 0) queue.splice(index, 1)
          pending.delete(key)
        }
      }
      reject(abortError())
    }
    signal.addEventListener("abort", leave, { once: true })
    current.promise.then(
      (image) => {
        signal.removeEventListener("abort", leave)
        if (!signal.aborted) resolve(image)
      },
      (error) => {
        signal.removeEventListener("abort", leave)
        if (!signal.aborted) reject(error)
      }
    )
  })
}

/** Test helper: an empty store. */
export function resetPageImagesForTests() {
  kept.clear()
  keptBytes = 0
  pending.clear()
  queue.length = 0
  inFlight = 0
}

/** For tests and diagnostics: how many page requests are running now. */
export function pageRequestsInFlight() {
  return inFlight
}
