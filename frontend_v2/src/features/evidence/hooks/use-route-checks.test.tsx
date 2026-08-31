/**
 * The list-labelling check: how it batches, what it narrows, and when it gives up.
 *
 * The badge this feeds is not a safety control, so most of what is asserted here
 * is about honesty rather than protection -- that a label never says something
 * the check did not say, and that a page which could not be checked is
 * unlabelled all the way across rather than in patches.
 */

import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import type { FileRouteCheck, RouteCheckResponse } from "@/types/evidence.types"
import { ROUTE_CHECK_BATCH_LIMIT, useRouteChecks } from "./use-route-checks"

const apiMocks = vi.hoisted(() => ({ routeCheck: vi.fn() }))

vi.mock("../api", () => ({ evidenceAPI: { routeCheck: apiMocks.routeCheck } }))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

function fileCheck(overrides: Partial<FileRouteCheck> & { file_id: string }): FileRouteCheck {
  return {
    file_name: `${overrides.file_id}.pdf`,
    claimants: [],
    detected_format: null,
    outcome: "not_native",
    blocks_document_processing: false,
    reason: null,
    ...overrides,
  }
}

function response(files: FileRouteCheck[]): RouteCheckResponse {
  const outcomes: Record<string, number> = {}
  for (const file of files) outcomes[file.outcome] = (outcomes[file.outcome] ?? 0) + 1
  return {
    case_id: "case-1",
    files,
    summary: {
      checked: files.length,
      native: files.filter((file) => file.outcome === "native").length,
      blocking: files.filter((file) => file.blocks_document_processing).length,
      outcomes,
    },
  }
}

/** Answer whatever was asked about, so a batch's shape shows up in the result. */
function answerEverything() {
  apiMocks.routeCheck.mockImplementation((_caseId: string, ids: string[]) =>
    Promise.resolve(response(ids.map((file_id) => fileCheck({ file_id }))))
  )
}

/** Padded so that string ordering matches numeric ordering; the hook sorts. */
function ids(count: number): string[] {
  return Array.from({ length: count }, (_, index) => `f${String(index).padStart(4, "0")}`)
}

/**
 * Renders against the ordinary case. Never used to test the absent-case path:
 * a default parameter is applied when the argument is `undefined`, so passing
 * `undefined` here would quietly become `"case-1"` and assert nothing. The one
 * test that needs no case calls `renderHook` itself.
 */
function renderChecks(fileIds: readonly string[], caseId = "case-1") {
  return renderHook(() => useRouteChecks(caseId, fileIds), { wrapper: createWrapper() })
}

beforeEach(() => {
  apiMocks.routeCheck.mockReset()
})

describe("useRouteChecks", () => {
  it("asks once for a page that fits in one batch", async () => {
    answerEverything()
    const { result } = renderChecks(["a", "b", "c"])

    await waitFor(() => expect(result.current.routes.size).toBe(3))
    expect(apiMocks.routeCheck).toHaveBeenCalledTimes(1)
    expect(apiMocks.routeCheck).toHaveBeenCalledWith("case-1", ["a", "b", "c"])
  })

  it("splits a page larger than the server will accept", async () => {
    // The reason this hook chunks at all. A full page of this list is 250 files
    // and the endpoint refuses more than fifty, so an unchunked request would
    // fail on every full page and the column would simply be empty.
    answerEverything()
    const page = ids(250)
    const { result } = renderChecks(page)

    await waitFor(() => expect(result.current.routes.size).toBe(250))
    expect(apiMocks.routeCheck).toHaveBeenCalledTimes(5)
    for (const [, batch] of apiMocks.routeCheck.mock.calls) {
      expect((batch as string[]).length).toBeLessThanOrEqual(ROUTE_CHECK_BATCH_LIMIT)
    }
    // Every id asked about exactly once, none invented.
    const asked = apiMocks.routeCheck.mock.calls.flatMap(([, batch]) => batch as string[])
    expect(asked.slice().sort()).toEqual(page.slice().sort())
    expect(new Set(asked).size).toBe(250)
  })

  it("sends a full batch rather than splitting early", async () => {
    // Guards the chunk arithmetic in the other direction: a chunker that emitted
    // 49 at a time would still pass the test above, while making 20% more
    // requests than the server requires.
    answerEverything()
    const { result } = renderChecks(ids(ROUTE_CHECK_BATCH_LIMIT))

    await waitFor(() => expect(result.current.routes.size).toBe(ROUTE_CHECK_BATCH_LIMIT))
    expect(apiMocks.routeCheck).toHaveBeenCalledTimes(1)
  })

  it("narrows an outcome this build does not know", async () => {
    // A service deployed ahead of this bundle can name an outcome that did not
    // exist when it was built. Left alone it reaches a `Record` lookup that
    // returns undefined, and React renders that as a badge with no text -- which
    // reads as an answer rather than as the absence of one.
    apiMocks.routeCheck.mockResolvedValue(
      response([fileCheck({ file_id: "a", outcome: "a_format_invented_next_year" })])
    )
    const { result } = renderChecks(["a"])

    await waitFor(() => expect(result.current.routes.size).toBe(1))
    expect(result.current.routes.get("a")?.outcome).toBe("undetermined")
  })

  it("keeps a known outcome exactly as sent", async () => {
    apiMocks.routeCheck.mockResolvedValue(
      response([
        fileCheck({ file_id: "a", outcome: "native", detected_format: "camt053" }),
        fileCheck({ file_id: "b", outcome: "ambiguous", claimants: ["camt053", "bai2"] }),
      ])
    )
    const { result } = renderChecks(["a", "b"])

    await waitFor(() => expect(result.current.routes.size).toBe(2))
    expect(result.current.routes.get("a")?.outcome).toBe("native")
    expect(result.current.routes.get("a")?.detected_format).toBe("camt053")
    expect(result.current.routes.get("b")?.outcome).toBe("ambiguous")
    expect(result.current.routes.get("b")?.claimants).toEqual(["camt053", "bai2"])
  })

  it("labels nothing at all when one batch of several fails", async () => {
    // The rule that makes an unlabelled row readable. An ordinary document is
    // deliberately unlabelled, so a bank file in the failed batch would look
    // exactly like a document that was checked and found ordinary. Losing the
    // whole column says "not working"; losing part of it says something false.
    let call = 0
    apiMocks.routeCheck.mockImplementation((_caseId: string, batch: string[]) => {
      call += 1
      return call === 2
        ? Promise.reject(new Error("service unavailable"))
        : Promise.resolve(response(batch.map((file_id) => fileCheck({ file_id }))))
    })

    const { result } = renderChecks(ids(150))

    await waitFor(() => expect(result.current.error).toBeTruthy())
    expect(result.current.routes.size).toBe(0)
  })

  it("does not ask when there is nothing to ask about", async () => {
    answerEverything()
    const { result } = renderChecks([])

    // Asserted on the first render rather than after settling, because an
    // empty list makes no request either way -- chunking nothing produces no
    // batches. What the `ids.length > 0` guard actually buys is that the query
    // never runs at all, and the only place that shows is here: a query that
    // is running reports `isLoading` on its first render, and a disabled one
    // never does. Asserting this after `waitFor` passes without the guard.
    expect(result.current.isLoading).toBe(false)

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(apiMocks.routeCheck).not.toHaveBeenCalled()
    expect(result.current.routes.size).toBe(0)
  })

  it("does not ask before there is a case", async () => {
    answerEverything()
    const { result } = renderHook(() => useRouteChecks(undefined, ["a"]), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(apiMocks.routeCheck).not.toHaveBeenCalled()
    expect(result.current.routes.size).toBe(0)
  })

  it("asks once for a file listed twice", async () => {
    answerEverything()
    const { result } = renderChecks(["a", "b", "a"])

    await waitFor(() => expect(result.current.routes.size).toBe(2))
    expect(apiMocks.routeCheck).toHaveBeenCalledWith("case-1", ["a", "b"])
  })

  it("treats a re-ordered list as the same question", async () => {
    // Sorting the ids is what makes this true. Without it, a list re-ordered by
    // clicking a column header is a different query key and a fresh round of
    // requests for answers already held.
    answerEverything()
    const { result, rerender } = renderHook(
      ({ list }: { list: string[] }) => useRouteChecks("case-1", list),
      { wrapper: createWrapper(), initialProps: { list: ["b", "a", "c"] } }
    )

    await waitFor(() => expect(result.current.routes.size).toBe(3))
    expect(apiMocks.routeCheck).toHaveBeenCalledTimes(1)

    rerender({ list: ["c", "b", "a"] })
    await waitFor(() => expect(result.current.routes.size).toBe(3))
    expect(apiMocks.routeCheck).toHaveBeenCalledTimes(1)
  })

  it("reports no answer as an empty map rather than as undefined", async () => {
    // Every caller reads this with `.get(id)`, so handing back undefined while
    // a check is in flight would mean a crash on first render rather than an
    // unlabelled row.
    answerEverything()
    const { result } = renderChecks(["a"])

    expect(result.current.routes.size).toBe(0)
    await waitFor(() => expect(result.current.routes.size).toBe(1))
  })
})

describe("the batch limit", () => {
  it("matches the limit the server actually enforces", () => {
    // Two numbers in two languages that have to agree. If the server's limit
    // were lowered and this one were not, every full page would fail the check
    // and the column would go quiet -- which looks like a page of ordinary
    // documents rather than like a broken request.
    const here = dirname(fileURLToPath(import.meta.url))
    const router = resolve(here, "../../../../../backend/routers/evidence.py")
    const source = readFileSync(router, "utf8")

    const declared = source.match(/^MAX_BATCH_SIZE\s*=\s*(\d+)/m)
    expect(declared, "MAX_BATCH_SIZE is no longer declared in backend/routers/evidence.py").toBeTruthy()
    expect(Number(declared![1])).toBe(ROUTE_CHECK_BATCH_LIMIT)

    // And that the route-check endpoint is still what it guards, rather than a
    // constant that has drifted to meaning something else.
    //
    // Scoped to that endpoint's own body rather than searched for anywhere in
    // the file. A whole-file search passes on the copy of this guard inside
    // `/process/background`, so it would stay green while route-check stopped
    // enforcing anything -- which a mutant proved by doing exactly that.
    const decorator = '@router.post("/route-check")'
    const opens = source.indexOf(decorator)
    expect(opens, "the route-check endpoint is no longer declared").toBeGreaterThan(-1)

    const next = source.indexOf("@router.", opens + decorator.length)
    const body = next === -1 ? source.slice(opens) : source.slice(opens, next)
    expect(body).toMatch(/len\(request\.file_ids\)\s*>\s*MAX_BATCH_SIZE/)
  })
})
