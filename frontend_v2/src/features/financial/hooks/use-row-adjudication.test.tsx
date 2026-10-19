/**
 * What the adjudication hook does with each of the six answers.
 *
 * The request layer is already covered by `api.adjudication.test.ts`, so
 * nothing here re-checks a URL for its own sake. What is checked is the three
 * things the hook adds on top of it, each of which fails quietly if it is
 * wrong.
 *
 * **A refusal must not read as a success.** Four of the six outcomes arrive
 * with a 200 and only two of those changed anything. React Query has no way to
 * know that: it sees a resolved promise and reports `isSuccess`, and a screen
 * wired to `isSuccess` will tell somebody a row was taken out of the case's
 * totals when the ledger just declined to take it out. So the tests below
 * assert on `data.applied` for every outcome, including the ones where the
 * request itself went perfectly.
 *
 * **The ledger must be refetched exactly when it moved.** A missed
 * invalidation leaves a row on screen in a list it has left, and a person then
 * reads that stale screen as the ledger's answer. An unnecessary one costs a
 * request. The tests seed a real ledger query and a real graph query into a
 * real cache and check which of the two the hook disturbed, rather than
 * spying on `invalidateQueries` and taking the argument on trust -- a spy
 * would go on passing after somebody changed the key the ledger reads under.
 *
 * **`rescues_period` must survive.** It is said in this response and in no
 * other place; the adjudication log deliberately does not carry it. The hook
 * composes the whole reading precisely so a caller cannot render the outcome
 * and lose it, and that is asserted here rather than assumed.
 *
 * The fetch layer is stubbed rather than the api module mocked, following
 * `api.adjudication.test.ts`. Mocking `../api` would also replace the closed
 * vocabularies the format readers import from it, and the readers would then
 * narrow every value against an empty list -- turning every outcome in every
 * test into "unrecognised" while the tests still looked like they were
 * exercising the real thing.
 */

import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import type { RowAdjudication } from "../api"
import type { RowAdjudicationReading } from "../lib/adjudication-format"
import { useRowAdjudication } from "./use-row-adjudication"

const here = dirname(fileURLToPath(import.meta.url))

const CASE = "case-1"

/** The key `use-ledger-transactions` reads under, with no params supplied. */
const LEDGER_KEY = ["financial-ledger", CASE, null]
/** A key from the Neo4j hooks, which an adjudication has no business touching. */
const GRAPH_KEY = ["financial", CASE, { mode: "transactions" }]

/**
 * A stub that builds a fresh response per call, for the reason
 * `api.adjudication.test.ts` gives: a `Response` body can only be read once,
 * so a shared instance kills the second call in a test with "Body is unusable",
 * which reads exactly like the code under test having failed.
 */
function answers(body: unknown, status = 200): void {
  vi.mocked(globalThis.fetch).mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      })
    )
  )
}

/** An adjudication answer with the fields a given test does not care about filled in. */
function answer(overrides: Partial<RowAdjudication> = {}): RowAdjudication {
  return {
    transaction_id: "txn-1",
    outcome: "quarantined",
    applied: true,
    reason: null,
    ledger_status: "quarantined",
    quarantine_reason: "adjudicated",
    adjudication_id: "adj-1",
    rescues_period: false,
    ...overrides,
  }
}

/**
 * A wrapper and the client behind it, with a ledger read and a graph read
 * already in the cache so the hook's invalidation has something real to hit or
 * miss.
 */
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  queryClient.setQueryData(LEDGER_KEY, { transactions: [] })
  queryClient.setQueryData(GRAPH_KEY, { transactions: [] })

  function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
  return { queryClient, Wrapper }
}

function invalidated(queryClient: QueryClient, key: unknown[]): boolean {
  return queryClient.getQueryState(key)?.isInvalidated === true
}

function requestedPath(): string {
  const raw = String(vi.mocked(globalThis.fetch).mock.calls[0][0])
  return new URL(raw, "http://loupe.test").pathname
}

function requestedQuery(): URLSearchParams {
  const raw = String(vi.mocked(globalThis.fetch).mock.calls[0][0])
  return new URL(raw, "http://loupe.test").searchParams
}

function sentBody(): unknown {
  const init = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit
  return JSON.parse(String(init.body))
}

describe("useRowAdjudication", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    answers(answer())
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  /* ---------------------------------------------------------------- *
   * The verb travels in the variables
   * ---------------------------------------------------------------- */

  it("sends a quarantine to the quarantine route and a release to the release route", async () => {
    // One hook covers both actions, so the action in the variables is the only
    // thing choosing between them. Getting that wrong puts a row back into the
    // totals when somebody asked for it to be taken out, and the answer looks
    // like a success either way.
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate of row 44.",
      })
    })
    expect(requestedPath()).toBe("/api/financial/transactions/txn-1/quarantine")

    vi.mocked(globalThis.fetch).mockClear()
    answers(answer({ outcome: "released", ledger_status: "admitted", quarantine_reason: null }))

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "release",
        reason: "Confirmed against the original statement.",
      })
    })
    expect(requestedPath()).toBe("/api/financial/transactions/txn-1/release")
  })

  it("carries the case in the query string and the person's words in the body", async () => {
    // The grounds are recorded verbatim against a named person. A reason that
    // ends up somewhere the endpoint does not read leaves a total that changed
    // with nothing on the record saying why.
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "The amount is illegible on the statement.",
      })
    })

    expect(requestedQuery().get("case_id")).toBe(CASE)
    expect(sentBody()).toEqual({ reason: "The amount is illegible on the statement." })
  })

  /* ---------------------------------------------------------------- *
   * A refusal is an answer, not a failure
   * ---------------------------------------------------------------- */

  it("resolves a refusal and reports that nothing was applied", async () => {
    // The endpoint turns only not_found and write_failed into HTTP errors.
    // `refused` arrives with a 200 and means the ledger declined; a caller
    // reading isSuccess as confirmation would announce a change that did not
    // happen.
    answers(
      answer({
        outcome: "refused",
        applied: false,
        reason: "The row is already held on other grounds.",
        rescues_period: null,
      })
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.isError).toBe(false)
    expect(result.current.data?.applied).toBe(false)
    expect(result.current.data?.outcome.value).toBe("refused")
  })

  it("reports unchanged as an answer that applied nothing", async () => {
    answers(
      answer({
        outcome: "unchanged",
        applied: false,
        adjudication_id: null,
        rescues_period: null,
      })
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    await waitFor(() => {
      expect(result.current.data?.applied).toBe(false)
      expect(result.current.data?.outcome.value).toBe("unchanged")
      // No decision was appended, so this attempt claims no id for one. An id
      // here would belong to whoever set the row aside earlier.
      expect(result.current.data?.adjudicationId).toBeNull()
    })
  })

  it("fails the mutation when the endpoint turns the outcome into an error", async () => {
    // not_found is a 404 and write_failed a 500, which are the two the router
    // deliberately puts on the browser's error path.
    answers({ detail: "No such transaction in this case." }, 404)
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          transactionId: "txn-1",
          action: "quarantine",
          reason: "Duplicate.",
        })
      ).rejects.toThrow("No such transaction in this case.")
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })

  /* ---------------------------------------------------------------- *
   * The answer is read whole
   * ---------------------------------------------------------------- */

  it("hands back the whole reading, including whether the removal balanced a statement", async () => {
    // rescues_period is said here and nowhere else. Composing the reading in
    // the hook is what stops a caller rendering the outcome and losing it.
    answers(answer({ rescues_period: true }))
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    // Both ways a caller can get at the answer, because either one being the
    // raw wire object would let the fact be dropped.
    let returned: RowAdjudicationReading | undefined
    await act(async () => {
      returned = await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    expect(returned?.rescue.raw).toBe(true)
    await waitFor(() => {
      expect(result.current.data?.rescue.raw).toBe(true)
      expect(result.current.data?.rescue.key).toBe("rescue-balanced")
      expect(result.current.data?.ledgerStatus?.value).toBe("quarantined")
      expect(result.current.data?.quarantineReason?.value).toBe("adjudicated")
    })
  })

  it("keeps an outcome this build cannot read, rather than blanking it", async () => {
    // A backend one version ahead can send a word this build has no name for.
    // The reading says so in its own label; it does not guess.
    answers(answer({ outcome: "deferred", applied: false, rescues_period: null }))
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    await waitFor(() => {
      expect(result.current.data?.outcome.value).toBeNull()
      expect(result.current.data?.outcome.raw).toBe("deferred")
      expect(result.current.data?.outcome.changedTheRow).toBeNull()
    })
  })

  it("surfaces a disagreement between the flag and the word instead of picking one", async () => {
    answers(answer({ outcome: "quarantined", applied: false }))
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    await waitFor(() => {
      expect(result.current.data?.appliedDisagreesWithOutcome).toBe(true)
      // What a person is told about whether the row moved comes from the flag.
      expect(result.current.data?.applied).toBe(false)
    })
  })

  /* ---------------------------------------------------------------- *
   * Which reads get refetched
   * ---------------------------------------------------------------- */

  it("refetches the ledger when a row is set aside", async () => {
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    expect(invalidated(queryClient, LEDGER_KEY)).toBe(true)
  })

  it("refetches the ledger when a row is let back in", async () => {
    // Both lists on the ledger screen are wrong afterwards: the row left one
    // and joined the other.
    answers(
      answer({
        outcome: "released",
        ledger_status: "admitted",
        quarantine_reason: null,
        rescues_period: null,
      })
    )
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "release",
        reason: "Confirmed against the original statement.",
      })
    })

    expect(invalidated(queryClient, LEDGER_KEY)).toBe(true)
  })

  it("leaves the ledger alone when the answer changed nothing", async () => {
    answers(
      answer({
        outcome: "unchanged",
        applied: false,
        adjudication_id: null,
        rescues_period: null,
      })
    )
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    expect(invalidated(queryClient, LEDGER_KEY)).toBe(false)
  })

  it("refetches the ledger when the flag and the word disagree", async () => {
    // A disagreement is not resolved by picking one. Refetching when nothing
    // moved costs a request; not refetching when something did leaves a row on
    // screen in a list it has left, and a person reads that as the answer.
    answers(answer({ outcome: "quarantined", applied: false }))
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    expect(invalidated(queryClient, LEDGER_KEY)).toBe(true)
  })

  it("leaves the ledger alone for an outcome this build cannot read", async () => {
    // Nothing is known about what an unrecognised word did, and the flag says
    // nothing was applied. Refetching on that would be guessing.
    answers(answer({ outcome: "deferred", applied: false, rescues_period: null }))
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    expect(invalidated(queryClient, LEDGER_KEY)).toBe(false)
  })

  it("does not touch the graph reads", async () => {
    // The relational ledger and the Neo4j graph are separate stores, not
    // projections of each other. A status change on a stored row does not
    // change a graph node, and refetching the graph here would assert a
    // relationship the write path does not have.
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(CASE), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        transactionId: "txn-1",
        action: "quarantine",
        reason: "Duplicate.",
      })
    })

    expect(invalidated(queryClient, LEDGER_KEY)).toBe(true)
    expect(invalidated(queryClient, GRAPH_KEY)).toBe(false)
  })

  /* ---------------------------------------------------------------- *
   * No case, no write
   * ---------------------------------------------------------------- */

  it("refuses to write when there is no case open, without reaching the network", async () => {
    // The sibling ingest hook asserts its case id instead, which is tolerable
    // on a path that only reads a file. This one changes what a case's totals
    // count, and a write addressed to case_id=undefined is not a request worth
    // making.
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRowAdjudication(undefined), { wrapper: Wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          transactionId: "txn-1",
          action: "quarantine",
          reason: "Duplicate.",
        })
      ).rejects.toThrow(/no case is open/i)
    })

    expect(vi.mocked(globalThis.fetch)).not.toHaveBeenCalled()
  })
})

/* ------------------------------------------------------------------ *
 * The key this hook invalidates is the key the ledger reads under
 * ------------------------------------------------------------------ */

describe("the invalidation key", () => {
  // The tests above seed LEDGER_KEY by hand, so they would keep passing if the
  // ledger read moved to a different key and the hook followed it nowhere.
  // This reads both files and requires them to still name the same prefix.
  it("matches the key use-ledger-transactions reads under", () => {
    const read = readFileSync(resolve(here, "./use-ledger-transactions.ts"), "utf8")
    expect(read).toContain('queryKey: ["financial-ledger", caseId,')

    const write = readFileSync(resolve(here, "./use-row-adjudication.ts"), "utf8")
    expect(write).toContain('queryKey: ["financial-ledger", caseId]')
  })

  it("is not a prefix of the graph hooks' keys", () => {
    // "financial-ledger" and "financial" are separate first segments, so
    // neither invalidation reaches the other's queries. Asserted because the
    // two names differ by a suffix and are easy to conflate on sight.
    const graph = readFileSync(resolve(here, "./use-financial-data.ts"), "utf8")
    expect(graph).toContain('queryKey: ["financial", caseId')
    expect(graph).not.toContain('"financial-ledger"')
  })
})
