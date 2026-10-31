import { afterEach, beforeEach, expect, it, vi } from "vitest"
import {
  HANDOFF_MS,
  MAX_IN_FLIGHT,
  keptPageImages,
  loadPageImage,
  pageRequestsInFlight,
  resetPageImagesForTests,
} from "./pdf-page-images"

const fetchFile = vi.fn()
const answers: Array<(value: unknown) => void> = []
function imageResponse(count = 9) {
  return {
    ok: true,
    headers: new Headers({ "content-type": "image/png", "X-PDF-Page-Count": String(count) }),
    blob: async () => new Blob(["page"], { type: "image/png" }),
  }
}
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  resetPageImagesForTests()
  answers.length = 0
  fetchFile.mockReset()
  fetchFile.mockImplementation(() => new Promise((resolve) => answers.push(resolve)))
  vi.stubGlobal("fetch", fetchFile)
})
afterEach(() => vi.unstubAllGlobals())

const want = (page: number, signal = new AbortController().signal) =>
  loadPageImage("file-a", page, { token: "t", signal })

it("runs at most three page requests at once and starts the next as one finishes", async () => {
  const pages = [1, 2, 3, 4, 5].map((page) => want(page))
  await flush()
  expect(MAX_IN_FLIGHT).toBe(3)
  expect(fetchFile).toHaveBeenCalledTimes(3)
  expect(pageRequestsInFlight()).toBe(3)
  answers[0](imageResponse())
  await pages[0]
  await flush()
  expect(fetchFile).toHaveBeenCalledTimes(4)
  expect(fetchFile.mock.calls.map((call) => call[0])).toEqual([1, 2, 3, 4].map(
    (page) => `/api/evidence/file-a/page/${page}/image`
  ))
})

it("joins a request already on its way and hands the answer on, then asks the server again", async () => {
  const one = want(1)
  const two = want(1)
  await flush()
  answers[0](imageResponse(9))
  const [a, b] = await Promise.all([one, two])
  expect(a).toBe(b)
  expect(a.pageCount).toBe(9)
  expect(await want(1)).toBe(a)
  expect(fetchFile).toHaveBeenCalledTimes(1)
  // Later views ask again, so withdrawn access is refused (the browser revalidates: 304 after the check).
  const now = performance.now()
  const clock = vi.spyOn(performance, "now").mockReturnValue(now + HANDOFF_MS + 1)
  const later = want(1)
  await flush()
  expect(fetchFile).toHaveBeenCalledTimes(2)
  expect(keptPageImages()).toEqual({ count: 0, bytes: 0 }) // the expired answer is no longer held
  answers[1]({ ok: false, status: 403 })
  await expect(later).rejects.toThrow("You do not currently have access")
  clock.mockRestore()
})

it("a caller arriving as a cancelled request is torn down starts a fresh one", async () => {
  const leaving = new AbortController()
  const first = want(1, leaving.signal)
  first.catch(() => undefined)
  await flush()
  leaving.abort()
  const again = want(1)
  await flush()
  expect(fetchFile).toHaveBeenCalledTimes(2)
  answers[0](Promise.reject(new DOMException("aborted", "AbortError")))
  answers[1](imageResponse())
  await expect(again).resolves.toMatchObject({ pageCount: 9 })
})

it("drops a queued page nobody wants any more, and aborts a running one", async () => {
  const leaving = [1, 2, 3, 4].map(() => new AbortController())
  const pages = leaving.map((controller, index) => want(index + 1, controller.signal))
  pages.forEach((promise) => promise.catch(() => undefined))
  await flush()
  leaving[3].abort() // page 4, still queued
  leaving[0].abort() // page 1, running
  expect(fetchFile.mock.calls[0][1].signal.aborted).toBe(true)
  answers[0](Promise.reject(new DOMException("aborted", "AbortError")))
  await flush()
  expect(fetchFile).toHaveBeenCalledTimes(3) // page 4 never asked for
  await expect(pages[3]).rejects.toThrow()
})

it("keeps no failed page, so a retry asks the server again", async () => {
  const first = want(2)
  await flush()
  answers[0]({ ok: false, status: 503 })
  await expect(first).rejects.toThrow("Page 2 could not be loaded")
  const second = want(2)
  await flush()
  answers[1](imageResponse())
  await second
  expect(fetchFile).toHaveBeenCalledTimes(2)
})

it("keeps each signed-in token's pages apart", async () => {
  const mine = want(1)
  await flush()
  answers[0](imageResponse())
  await mine
  const theirs = loadPageImage("file-a", 1, { token: "other", signal: new AbortController().signal })
  await flush()
  expect(fetchFile).toHaveBeenCalledTimes(2)
  answers[1](imageResponse())
  await theirs
})
