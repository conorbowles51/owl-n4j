/**
 * The gate's behaviour, and the assertion that it is the only way through.
 *
 * The second half of this file walks `src` and fails if any module other than
 * the gate itself asks for processing directly.  That check is the substance of
 * the claim the hook's own header makes: a gate everyone is asked politely to
 * use is a convention, and conventions are what produced the seven separate
 * copies this hook replaced.  A gate a test enforces is a gate.
 */

import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { readFileSync, readdirSync } from "node:fs"
import { dirname, join, relative, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import type { FileRouteCheck, RouteCheckResponse } from "@/types/evidence.types"
import type { HeldRequest } from "./use-guarded-process"
import { describeHold, useGuardedProcess } from "./use-guarded-process"

const apiMocks = vi.hoisted(() => ({
  routeCheck: vi.fn(),
  processBackground: vi.fn(),
}))

vi.mock("../api", () => ({
  evidenceAPI: {
    routeCheck: apiMocks.routeCheck,
    processBackground: apiMocks.processBackground,
  },
}))

const toastMocks = vi.hoisted(() => ({
  warning: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock("sonner", () => ({ toast: toastMocks }))

/** Reset every mock the gate touches, so no test inherits another's calls. */
function resetMocks() {
  apiMocks.routeCheck.mockReset()
  apiMocks.processBackground.mockReset()
  apiMocks.processBackground.mockResolvedValue({ task_id: "task-1" })
  toastMocks.warning.mockReset()
  toastMocks.success.mockReset()
  toastMocks.error.mockReset()
  toastMocks.info.mockReset()
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

/** A check result for one file, with the fields a test does not care about filled in. */
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

function renderGate() {
  return renderHook(() => useGuardedProcess("case-1"), { wrapper: createWrapper() })
}

describe("starting a process request", () => {
  beforeEach(resetMocks)

  it("checks the same file ids it is about to process", async () => {
    apiMocks.routeCheck.mockResolvedValue(response([fileCheck({ file_id: "a" })]))
    const { result } = renderGate()

    await act(async () => {
      await result.current.start({ fileIds: ["a"] })
    })

    expect(apiMocks.routeCheck).toHaveBeenCalledWith("case-1", ["a"])
  })

  it("processes files the check cleared", async () => {
    apiMocks.routeCheck.mockResolvedValue(
      response([fileCheck({ file_id: "a" }), fileCheck({ file_id: "b" })])
    )
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: ["a", "b"], profile: "default" })
    })

    expect(outcome).toBe("started")
    expect(apiMocks.processBackground).toHaveBeenCalledWith(
      "case-1",
      ["a", "b"],
      "default",
      undefined,
      undefined
    )
    expect(result.current.held).toBeNull()
    // Nothing was held, so nothing is announced -- the caller owns the success
    // message, and a warning here would contradict it.
    expect(toastMocks.warning).not.toHaveBeenCalled()
  })

  it("does not check or process an empty selection", async () => {
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: [] })
    })

    expect(outcome).toBe("empty")
    expect(apiMocks.routeCheck).not.toHaveBeenCalled()
    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(toastMocks.warning).not.toHaveBeenCalled()
  })

  it("holds the whole request when one file is a bank statement", async () => {
    // The blocked file is second on purpose: an implementation that stopped at
    // the first answer would pass with it first and fail here.
    apiMocks.routeCheck.mockResolvedValue(
      response([
        fileCheck({ file_id: "a" }),
        fileCheck({
          file_id: "b",
          outcome: "native",
          detected_format: "camt053",
          claimants: ["camt053"],
          blocks_document_processing: true,
        }),
      ])
    )
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: ["a", "b"] })
    })

    expect(outcome).toBe("held")
    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held?.held.map((file) => file.file_id)).toEqual(["b"])
    expect(result.current.held?.cleared).toEqual(["a"])
    expect(result.current.held?.checkError).toBeNull()
    // Said out loud by the hook itself. A caller that ignores the return value
    // must still not be able to leave a blocked request looking like a button
    // that did nothing.
    expect(toastMocks.warning).toHaveBeenCalledTimes(1)
    expect(toastMocks.warning).toHaveBeenCalledWith(
      "1 file looks like bank records and was held back. 1 other file is ready to process."
    )
  })

  it("holds a file the local rule blocks even when the service says it does not", async () => {
    // An older service computing `blocks_document_processing` without knowing
    // about an outcome added since. The two disagreeing must resolve towards
    // holding, so the flag alone is not enough to get a native file through.
    apiMocks.routeCheck.mockResolvedValue(
      response([
        fileCheck({ file_id: "a", outcome: "native", blocks_document_processing: false }),
      ])
    )
    const { result } = renderGate()

    await act(async () => {
      await result.current.start({ fileIds: ["a"] })
    })

    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held?.held.map((file) => file.file_id)).toEqual(["a"])
  })

  it("holds a file the service blocks even when the local rule does not", async () => {
    // The other direction of the same disagreement, and the one the local rule
    // cannot reach on its own: `not_native` is not a blocking outcome here, so
    // a service that blocks for a reason its outcome word does not carry --
    // a policy, a quarantine, a newer rule -- is only heard if the flag is
    // consulted as well. Dropping `|| file.blocks_document_processing` passes
    // every other test in this file.
    apiMocks.routeCheck.mockResolvedValue(
      response([
        fileCheck({ file_id: "a", outcome: "not_native", blocks_document_processing: true }),
      ])
    )
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: ["a"] })
    })

    expect(outcome).toBe("held")
    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held?.held.map((file) => file.file_id)).toEqual(["a"])
    expect(result.current.held?.cleared).toEqual([])
  })

  it("holds a file whose outcome this build has never heard of", async () => {
    apiMocks.routeCheck.mockResolvedValue(
      response([
        fileCheck({ file_id: "a", outcome: "quarantined", blocks_document_processing: false }),
      ])
    )
    const { result } = renderGate()

    await act(async () => {
      await result.current.start({ fileIds: ["a"] })
    })

    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    // Narrowed at the edge, so what the dialog renders is a known outcome
    // rather than the word that arrived on the wire.
    expect(result.current.held?.held[0].outcome).toBe("undetermined")
  })

  it("holds everything when the check itself fails", async () => {
    // The endpoint missing because the backend is older than this bundle is
    // the case that matters: it must not read as "nothing to worry about".
    apiMocks.routeCheck.mockRejectedValue(new Error("404 Not Found"))
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: ["a", "b"] })
    })

    expect(outcome).toBe("held")
    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held?.checkError).toBe("404 Not Found")
    expect(result.current.held?.cleared).toEqual([])
    expect(result.current.held?.held).toEqual([])
    expect(toastMocks.warning).toHaveBeenCalledWith(
      "Nothing was sent: the files could not be checked. 404 Not Found"
    )
  })

  it("holds when the check answered for fewer files than were asked about", async () => {
    apiMocks.routeCheck.mockResolvedValue(response([fileCheck({ file_id: "a" })]))
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: ["a", "b"] })
    })

    expect(outcome).toBe("held")
    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held?.checkError).toContain("1 of 2")
    // `b` was never spoken for, so it is not on the list that may be released.
    expect(result.current.held?.cleared).toEqual(["a"])
  })

  it("reports a failed send rather than throwing it at the caller", async () => {
    // Seven call sites awaiting a promise that can throw is seven chances to
    // forget a `try`. The hook says so instead, and the caller sees an outcome.
    apiMocks.routeCheck.mockResolvedValue(response([fileCheck({ file_id: "a" })]))
    apiMocks.processBackground.mockRejectedValue(new Error("worker unavailable"))
    const { result } = renderGate()

    let outcome
    await act(async () => {
      outcome = await result.current.start({ fileIds: ["a"] })
    })

    expect(outcome).toBe("failed")
    expect(toastMocks.error).toHaveBeenCalledWith("worker unavailable")
    // Nothing was held: the check cleared the file, the send is what broke, so
    // there is no list of bank files to offer anyone.
    expect(result.current.held).toBeNull()
  })

  it("reports that it is checking while the check is in flight", async () => {
    let settle: (value: RouteCheckResponse) => void = () => {}
    apiMocks.routeCheck.mockReturnValue(
      new Promise<RouteCheckResponse>((res) => {
        settle = res
      })
    )
    const { result } = renderGate()

    let started: Promise<unknown>
    act(() => {
      started = result.current.start({ fileIds: ["a"] })
    })
    await waitFor(() => expect(result.current.isChecking).toBe(true))

    await act(async () => {
      settle(response([fileCheck({ file_id: "a" })]))
      await started
    })
    expect(result.current.isChecking).toBe(false)
  })
})

describe("what happens to a held request", () => {
  beforeEach(resetMocks)

  async function holdOneOfTwo() {
    apiMocks.routeCheck.mockResolvedValue(
      response([
        fileCheck({ file_id: "a" }),
        fileCheck({ file_id: "b", outcome: "native", blocks_document_processing: true }),
      ])
    )
    const rendered = renderGate()
    await act(async () => {
      await rendered.result.current.start({ fileIds: ["a", "b"], profile: "default" })
    })
    return rendered
  }

  it("releases only the cleared files, never the held ones", async () => {
    const { result } = await holdOneOfTwo()

    let count
    await act(async () => {
      count = await result.current.release()
    })

    expect(count).toBe(1)
    expect(apiMocks.processBackground).toHaveBeenCalledWith(
      "case-1",
      ["a"],
      "default",
      undefined,
      undefined
    )
    expect(result.current.held).toBeNull()
  })

  it("releases nothing when the check failed, because nothing was learned", async () => {
    apiMocks.routeCheck.mockRejectedValue(new Error("network down"))
    const { result } = renderGate()
    await act(async () => {
      await result.current.start({ fileIds: ["a", "b"] })
    })

    let count
    await act(async () => {
      count = await result.current.release()
    })

    expect(count).toBe(0)
    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held).toBeNull()
  })

  it("reports nothing sent when releasing the cleared files fails", async () => {
    const { result } = await holdOneOfTwo()
    apiMocks.processBackground.mockRejectedValue(new Error("worker unavailable"))

    let count
    await act(async () => {
      count = await result.current.release()
    })

    // One file was cleared, but none arrived. Returning 1 here would let a
    // dialog report a success that did not happen.
    expect(count).toBe(0)
    expect(toastMocks.error).toHaveBeenCalledWith("worker unavailable")
  })

  it("dismisses without processing anything", async () => {
    const { result } = await holdOneOfTwo()

    act(() => result.current.dismiss())

    expect(apiMocks.processBackground).not.toHaveBeenCalled()
    expect(result.current.held).toBeNull()
  })
})

describe("describing a hold", () => {
  /** A held request with the fields a given case does not exercise emptied. */
  function heldRequest(overrides: Partial<HeldRequest> = {}): HeldRequest {
    return {
      request: { fileIds: ["a"] },
      held: [],
      cleared: [],
      summary: null,
      checkError: null,
      ...overrides,
    }
  }

  function heldFile(id: string) {
    return {
      ...fileCheck({ file_id: id, blocks_document_processing: true }),
      outcome: "native" as const,
    }
  }

  it("says nothing was sent when nothing was learned", () => {
    expect(
      describeHold(heldRequest({ checkError: "network down" }))
    ).toBe("Nothing was sent: the files could not be checked. network down")
  })

  it("reads as a whole sentence even with no reason to give", () => {
    // `checkError` is typed nullable, so the message must not end up with a
    // dangling "undefined" or a trailing space when it is null.
    expect(describeHold(heldRequest())).toBe(
      "Nothing was sent: the files could not be checked."
    )
  })

  it("agrees in number on both halves", () => {
    expect(
      describeHold(heldRequest({ held: [heldFile("a")], cleared: ["b"] }))
    ).toBe("1 file looks like bank records and was held back. 1 other file is ready to process.")
    expect(
      describeHold(
        heldRequest({ held: [heldFile("a"), heldFile("b")], cleared: ["c", "d"] })
      )
    ).toBe("2 files look like bank records and were held back. 2 other files are ready to process.")
  })

  it("does not mention other files when there are none", () => {
    expect(describeHold(heldRequest({ held: [heldFile("a")] }))).toBe(
      "1 file looks like bank records and was held back."
    )
  })

  it("still reports the sorted files when the check answered for only some", () => {
    // The case the first version of this function got wrong. `checkError` is
    // set here too, but files *were* sorted and the cleared ones can still be
    // released, so calling this "nothing was sent" would misdescribe it.
    const message = describeHold(
      heldRequest({
        held: [heldFile("a")],
        cleared: ["b"],
        checkError: "The check returned no answer for 1 of 3 files.",
      })
    )
    expect(message).toBe(
      "1 file looks like bank records and was held back. " +
        "The check returned no answer for 1 of 3 files. 1 other file is ready to process."
    )
    expect(message).not.toContain("Nothing was sent")
  })

  it("reports an unanswered file even when nothing else was held", () => {
    // Held is empty and cleared is not: the only reason this request stopped
    // is the unanswered file, so the reason is the whole message.
    expect(
      describeHold(
        heldRequest({
          cleared: ["a"],
          checkError: "The check returned no answer for 1 of 2 files.",
        })
      )
    ).toBe("The check returned no answer for 1 of 2 files. 1 other file is ready to process.")
  })
})

// --------------------------------------------------------------------------
// The gate is the only way through
// --------------------------------------------------------------------------

const here = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(here, "../../../")

/** Every `.ts`/`.tsx` file under `src`, excluding tests. */
function sourceFiles(dir: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      found.push(...sourceFiles(full))
      continue
    }
    if (!/\.tsx?$/.test(entry.name)) continue
    // Test files are excluded because a test that mocks the API is not a door
    // a user can walk through -- this very file names `processBackground` in
    // its own mock. Product code has no such excuse.
    if (/\.test\.tsx?$/.test(entry.name)) continue
    found.push(full)
  }
  return found
}

/**
 * The two modules allowed to ask for processing: the wire wrapper, and the
 * gate that is the only thing permitted to call it.
 */
const ALLOWED = [
  "features/evidence/api.ts",
  "features/evidence/hooks/use-guarded-process.ts",
]

/** Asking the pipeline to process files, by any of the routes that exist. */
const WAYS_TO_ASK = [
  /processBackground/,
  /evidenceAPI\s*\.\s*process\s*\(/,
  /["'`]\/api\/evidence\/process/,
]

describe("no door around the gate", () => {
  const files = sourceFiles(SRC)

  it("found a plausible number of source files to check", () => {
    // Without this, a walk that silently returned nothing would pass the
    // assertion below while checking nothing at all.
    expect(files.length).toBeGreaterThan(100)
  })

  it("the allowed modules really do contain what the check looks for", () => {
    // The other half of the same worry. If `processBackground` were renamed,
    // every pattern below would stop matching everywhere and the real check
    // would pass by finding nothing rather than by there being nothing.
    //
    // Definitions and calls are matched, never the bare word. The first version
    // of this guard asserted `/processBackground/` against `api.ts`, which the
    // doc comment on `routeCheck` satisfies all by itself -- so the guard would
    // have stayed green through a rename of the one function it exists to
    // guard, and the real check below would then have found nothing anywhere.
    const api = readFileSync(resolve(SRC, ALLOWED[0]), "utf8")
    const gate = readFileSync(resolve(SRC, ALLOWED[1]), "utf8")
    expect(api).toMatch(/processBackground\s*:/)
    expect(api).toMatch(/["'`]\/api\/evidence\/process/)
    expect(api).toMatch(/\bprocess\s*:/)
    expect(gate).toMatch(/evidenceAPI\s*\.\s*processBackground\s*\(/)
  })

  it("every exemption is still load-bearing", () => {
    // An exemption has to keep earning itself. A path left on this list after
    // its last call was removed is a standing permission nobody decided to
    // grant, and the next call added to that file would go unnoticed -- which
    // is exactly the state the seven call sites were in before the gate.
    for (const path of ALLOWED) {
      const text = readFileSync(resolve(SRC, path), "utf8")
      expect(
        WAYS_TO_ASK.some((pattern) => pattern.test(text)),
        `${path} is exempt but no longer asks the pipeline for anything`
      ).toBe(true)
    }
  })

  it("no module outside the gate asks the pipeline to process a file", () => {
    const allowed = new Set(ALLOWED.map((path) => resolve(SRC, path)))
    const offenders: string[] = []

    for (const file of files) {
      if (allowed.has(file)) continue
      const text = readFileSync(file, "utf8")
      if (WAYS_TO_ASK.some((pattern) => pattern.test(text))) {
        offenders.push(relative(SRC, file))
      }
    }

    // Named rather than counted, so the failure says which file to fix.
    expect(offenders).toEqual([])
  })
})
