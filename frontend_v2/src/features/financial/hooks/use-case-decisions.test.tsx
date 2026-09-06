/**
 * What the decisions hook adds on top of the request, and what it must not lose.
 *
 * `api.decisions.test.ts` already holds `getCaseDecisions` against the Python,
 * so nothing here re-checks a URL for its own sake. What is checked is the four
 * things this layer can get wrong in a way that produces a screen which looks
 * right.
 *
 * **Zero has to survive the trip.** `limit: 0` and `offset: 0` are requests,
 * not absences. Anything on this path that reaches for truthiness turns an
 * explicit ask for the first page into whatever the backend defaults to, and
 * the page that comes back is a perfectly valid page -- just not the one that
 * was asked for. `getCaseDecisions` guards with `!== undefined`; these tests
 * exist because a coercion in the hook would undo that guard one layer up and
 * nothing would fail.
 *
 * **The envelope has to arrive whole.** `total` and `truncated` are the only
 * things standing between this screen and a history that quietly stops. A hook
 * that handed back `decisions` alone would render a page of entries with no way
 * to say that more were left off, and every test about the entries themselves
 * would still pass.
 *
 * **The key has to be the case, the filters, and nothing shared with the
 * ledger.** Two failures hide here. A key that ignored the filters would answer
 * a request for the second page out of the cache with the first page's rows. A
 * key under the ledger's prefix would be swept by every ledger invalidation and
 * would tie a log that outlives its subjects to the list of those subjects. Both
 * are asserted against a real cache rather than by reading the hook's source.
 *
 * **No case must mean no request.** Asserted on `fetch` rather than on a status
 * flag, because a request addressed to `case_id=undefined` is the thing that
 * must not leave.
 *
 * The fetch layer is stubbed rather than `../api` mocked, following
 * `use-row-adjudication.test.tsx`. Mocking the module would replace the closed
 * vocabularies the format readers import from it.
 */

import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { DecisionRecord, DecisionsResponse } from "../api"
import { useCaseDecisions } from "./use-case-decisions"

const CASE = "case-1"

/** The key this hook reads under when no filters are supplied. */
const DECISIONS_KEY = ["financial-decisions", CASE, null]
/** The key `use-ledger-transactions` reads under, which this one must not share. */
const LEDGER_KEY = ["financial-ledger", CASE, null]

/**
 * A stub that builds a fresh response per call, for the reason
 * `use-row-adjudication.test.tsx` gives: a `Response` body can only be read
 * once, so a shared instance kills a second call with "Body is unusable",
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

function record(overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    id: "dec-1",
    case_id: CASE,
    subject_type: "transaction",
    subject_id: "txn-1",
    subject_sequence: 1,
    decision: "quarantine_row",
    reason: "The amount is illegible on the statement.",
    before: { ledger_status: "admitted" },
    after: { ledger_status: "quarantined" },
    actor_name: "Alex Rivera",
    actor_email: "alex@owl.test",
    actor_user_id: "user-1",
    ingestion_run_id: null,
    recorded_at: "2026-09-01T10:00:00Z",
    by_machine: false,
    ...overrides,
  }
}

/** A page with the fields a given test does not care about filled in. */
function page(overrides: Partial<DecisionsResponse> = {}): DecisionsResponse {
  return {
    case_id: CASE,
    decisions: [record()],
    total: 1,
    limit: 100,
    offset: 0,
    truncated: false,
    ...overrides,
  }
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
  return { queryClient, Wrapper }
}

/**
 * The query string of one call, by index.
 *
 * Indexed rather than fixed to the first call because several tests below make
 * a second request on purpose and care about that one.
 */
function requestedQuery(call = 0): URLSearchParams {
  const raw = String(vi.mocked(globalThis.fetch).mock.calls[call][0])
  return new URL(raw, "http://loupe.test").searchParams
}

function requestedPath(call = 0): string {
  const raw = String(vi.mocked(globalThis.fetch).mock.calls[call][0])
  return new URL(raw, "http://loupe.test").pathname
}

function invalidated(queryClient: QueryClient, key: unknown[]): boolean {
  return queryClient.getQueryState(key)?.isInvalidated === true
}

/**
 * Render and wait for the answer.
 *
 * Takes an options object rather than a defaulted `caseId` parameter. A
 * defaulted parameter cannot express "not supplied": passing `undefined` to
 * `caseId: string | undefined = CASE` takes the default, so the test written to
 * prove the no-case behaviour would run with a case open and fail against a
 * real request, which reads like a broken harness rather than a wrong
 * assertion.
 */
async function read(
  options: {
    caseId?: string | undefined
    params?: Parameters<typeof useCaseDecisions>[1]
    settle?: boolean
  } = {}
) {
  const caseId = "caseId" in options ? options.caseId : CASE
  const { queryClient, Wrapper } = createWrapper()
  const { result, rerender } = renderHook(
    (props: { params?: Parameters<typeof useCaseDecisions>[1] }) =>
      useCaseDecisions(caseId, props.params),
    { wrapper: Wrapper, initialProps: { params: options.params } }
  )
  if (options.settle !== false) {
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  }
  return { queryClient, result, rerender }
}

describe("useCaseDecisions", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    answers(page())
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  /* ---------------------------------------------------------------- *
   * Zero is a request, not an absence
   * ---------------------------------------------------------------- */

  it("sends limit 0 and offset 0 rather than dropping them", async () => {
    // The whole reason the hook forwards with `?.` and nothing else. A
    // truthiness guard here would swallow both and the backend would answer
    // with its own defaults -- a real page, containing rows, that nobody asked
    // for. Nothing downstream can tell the difference.
    await read({ params: { limit: 0, offset: 0 } })

    expect(requestedQuery().get("limit")).toBe("0")
    expect(requestedQuery().get("offset")).toBe("0")
  })

  it("omits limit and offset entirely when they were not supplied", async () => {
    // The other half of the same guard. Sending `limit=` or `limit=undefined`
    // would be a different request from sending nothing, and the backend's own
    // default is the intended answer when the caller has no opinion.
    await read({ params: {} })

    expect(requestedQuery().has("limit")).toBe(false)
    expect(requestedQuery().has("offset")).toBe(false)
  })

  it("asks for nothing but the case when no params are given at all", async () => {
    await read()

    expect(requestedPath()).toBe("/api/financial/decisions")
    expect([...requestedQuery().keys()]).toEqual(["case_id"])
    expect(requestedQuery().get("case_id")).toBe(CASE)
  })

  /* ---------------------------------------------------------------- *
   * Every filter reaches the wire under the backend's own name
   * ---------------------------------------------------------------- */

  it("forwards each filter under the name the endpoint reads", async () => {
    // The hook names these in camel case and the endpoint reads snake case. A
    // parameter that arrives misspelled is ignored by the backend rather than
    // refused, so the page comes back wider than the one asked for and looks
    // like a complete history of something it is not.
    await read({
      params: {
        subjectType: "source_document",
        subjectId: "doc-9",
        decision: "supersede_duplicate",
        limit: 25,
        offset: 50,
      },
    })

    const qs = requestedQuery()
    expect(qs.get("case_id")).toBe(CASE)
    expect(qs.get("subject_type")).toBe("source_document")
    expect(qs.get("subject_id")).toBe("doc-9")
    expect(qs.get("decision")).toBe("supersede_duplicate")
    expect(qs.get("limit")).toBe("25")
    expect(qs.get("offset")).toBe("50")
  })

  it("sends a subject id without a subject type", async () => {
    // Allowed on purpose: the records name their own kind and the read is
    // scoped to the case, so a subject from another matter comes back empty
    // rather than answered. A hook that required the pair would make the
    // narrower read impossible to ask for.
    await read({ params: { subjectId: "txn-7" } })

    expect(requestedQuery().get("subject_id")).toBe("txn-7")
    expect(requestedQuery().has("subject_type")).toBe(false)
  })

  /* ---------------------------------------------------------------- *
   * The page arrives whole
   * ---------------------------------------------------------------- */

  it("hands back the whole page, including how much of the record was left off", async () => {
    // `total` and `truncated` are the only things that let a screen say the
    // history it is showing is partial. A hook that returned `decisions` alone
    // would pass every test about the entries and still produce a screen that
    // quietly stops.
    answers(
      page({
        decisions: [record({ id: "dec-1" }), record({ id: "dec-2", subject_sequence: 2 })],
        total: 412,
        limit: 2,
        offset: 0,
        truncated: true,
      })
    )
    const { result } = await read()

    expect(result.current.data).toEqual({
      case_id: CASE,
      decisions: [record({ id: "dec-1" }), record({ id: "dec-2", subject_sequence: 2 })],
      total: 412,
      limit: 2,
      offset: 0,
      truncated: true,
    })
  })

  it("reports the limit the backend applied rather than the one that was asked for", async () => {
    // A limit above the cap is capped and answered, not refused. The bounds are
    // deliberately not mirrored on this side, so the response is the only place
    // the real page size is stated, and a hook that dropped it would leave a
    // caller believing it had 900 entries when it had 500.
    answers(page({ limit: 500, total: 900, truncated: true }))
    const { result } = await read({ params: { limit: 900 } })

    expect(requestedQuery().get("limit")).toBe("900")
    expect(result.current.data?.limit).toBe(500)
  })

  it("keeps a record's raw subject and decision words rather than narrowing them", async () => {
    // Narrowing belongs at the edge, in `lib/decision-format.ts`, and a member
    // this build has never heard of has to reach it to be labelled
    // unrecognised. A hook that filtered or defaulted unknown words would make
    // a decision disappear from a case's history instead.
    answers(page({ decisions: [record({ decision: "invented_by_a_newer_backend" })] }))
    const { result } = await read()

    expect(result.current.data?.decisions[0].decision).toBe("invented_by_a_newer_backend")
  })

  /* ---------------------------------------------------------------- *
   * The key: the case, the filters, and not the ledger's
   * ---------------------------------------------------------------- */

  it("caches under the case and the filters", async () => {
    const { queryClient, result } = await read()

    expect(queryClient.getQueryData(DECISIONS_KEY)).toEqual(result.current.data)
  })

  it("fetches again when the filters change rather than answering from the first page", async () => {
    // The failure this catches is the worst one available to a paged read: a
    // key that ignored its params would serve the request for the second page
    // out of the cache, and the screen would show the first page's rows under
    // the second page's heading.
    const { result, rerender } = await read({ params: { offset: 0, limit: 2 } })
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1)

    answers(page({ decisions: [record({ id: "dec-3" })], offset: 2, limit: 2, total: 5, truncated: true }))
    rerender({ params: { offset: 2, limit: 2 } })

    await waitFor(() => expect(result.current.data?.offset).toBe(2))
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(2)
    expect(requestedQuery(1).get("offset")).toBe("2")
    expect(result.current.data?.decisions[0].id).toBe("dec-3")
  })

  it("is not swept by an invalidation of the ledger", async () => {
    // The log is appended to and outlives what it is about: a purge writes its
    // decision and then deletes the row. Sharing the ledger's prefix would
    // refetch the whole history on every read of a list of rows and would tie
    // the record to the subjects it survives.
    const { queryClient } = await read()
    queryClient.setQueryData(LEDGER_KEY, { transactions: [] })
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1)

    await queryClient.invalidateQueries({ queryKey: ["financial-ledger", CASE] })

    // The ledger's own key was reached, so the invalidation did happen and the
    // assertion below is about the decisions key being out of its scope rather
    // than about nothing having been invalidated at all.
    expect(invalidated(queryClient, LEDGER_KEY)).toBe(true)
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1)
  })

  it("is refetched by an invalidation of its own prefix", async () => {
    // The other direction of the same fact. Without it the test above would
    // also pass against a key no invalidation could ever reach, and the panel's
    // refetch would silently do nothing.
    //
    // Asserted on the refetch and not on `isInvalidated`, which is the trap
    // here: this query has a live observer, so invalidating it starts a refetch
    // immediately and the flag is cleared again the moment that refetch
    // succeeds. Reading the flag afterwards gives false and looks exactly like
    // the key having been missed. `use-row-adjudication.test.tsx` can read the
    // flag only because the keys it seeds have no observer watching them.
    const { queryClient } = await read()
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1)

    await queryClient.invalidateQueries({ queryKey: ["financial-decisions", CASE] })

    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(2))
  })

  /* ---------------------------------------------------------------- *
   * No case, no request
   * ---------------------------------------------------------------- */

  it("makes no request at all when there is no case open", async () => {
    // Asserted on `fetch` rather than on a status flag. What must not happen is
    // a request going out addressed to `case_id=undefined`, which the backend
    // would answer for no case or refuse, and either way the screen would be
    // reporting on nothing.
    const { result } = await read({ caseId: undefined, settle: false })

    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"))
    expect(result.current.isPending).toBe(true)
    expect(vi.mocked(globalThis.fetch)).not.toHaveBeenCalled()
  })

  it("surfaces a failed read as an error rather than an empty history", async () => {
    // An empty page and a page that could not be read are different answers,
    // and only one of them means the case decided nothing. A hook that
    // swallowed the failure into `data: undefined` would let a panel render
    // "No decisions match this view" over a request that never succeeded.
    answers({ detail: "db exploded" }, 500)
    const { result } = await read({ settle: false })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })
})
