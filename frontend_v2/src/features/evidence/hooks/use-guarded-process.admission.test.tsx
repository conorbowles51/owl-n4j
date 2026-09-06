import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useGuardedProcess } from "./use-guarded-process"

const toast = vi.hoisted(() => ({ error: vi.fn() }))
vi.mock("sonner", () => ({ toast }))
const file = (id: string, outcome = "ambiguous") => ({
  file_id: id,
  file_name: `${id}.dat`,
  outcome,
  detected_format: null,
  claimants: [],
  reason: null,
  blocks_document_processing: outcome !== "not_native",
})
const answer = (id = "a", outcome = "admitted") => ({
  file_id: id,
  outcome,
  admitted: outcome === "admitted",
  routed_to: outcome === "admitted" ? "document_pipeline" : "held",
  reason: "Reviewed",
  route_outcome: "ambiguous",
  detected_format: null,
  claimants: [],
  adjudication_id: outcome === "admitted" ? "decision-1" : null,
})
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  })
const blocked = (id: string) =>
  json(
    {
      detail: {
        error: "unadmitted_files",
        message: "Held by server",
        held: [
          {
            file_id: id,
            file_name: `${id}.dat`,
            route_outcome: "ambiguous",
            detected_format: null,
            claimants: ["bai2", "mt940"],
          },
        ],
      },
    },
    409
  )
const fetchMock = vi.fn<typeof fetch>()

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  client.setQueryData(["financial-decisions", "case-1"], {})
  client.setQueryData(["financial-decisions", "other-case"], {})
  function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return {
    ...renderHook(({ caseId }) => useGuardedProcess(caseId), {
      wrapper: Wrapper,
      initialProps: { caseId: "case-1" },
    }),
    client,
  }
}
function route(files = [file("a"), file("b"), file("c", "not_native")]) {
  fetchMock.mockResolvedValueOnce(
    json({
      case_id: "case-1",
      files,
      summary: { checked: files.length, native: 0, blocking: 2, outcomes: {} },
    })
  )
}
const request = {
  fileIds: ["a", "b", "c"],
  profile: "detailed",
  maxWorkers: 3,
  imageProvider: "gemini",
}

beforeEach(() => {
  fetchMock.mockReset()
  toast.error.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe("held file admission through the real API clients", () => {
  it("records first, then sends only the explicitly selected file with the original processing settings", async () => {
    route()
    const { result, client } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    fetchMock.mockResolvedValueOnce(json(answer()))
    await act(async () => {
      await result.current.recordAdmission("a", "  Reviewed the original  ")
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual({
      reason: "  Reviewed the original  ",
    })
    expect(
      client.getQueryState(["financial-decisions", "case-1"])?.isInvalidated
    ).toBe(true)
    expect(
      client.getQueryState(["financial-decisions", "other-case"])?.isInvalidated
    ).toBe(false)
    fetchMock.mockResolvedValueOnce(json({ task_id: "task-1" }))
    await act(async () => {
      expect(await result.current.processAdmitted("a")).toBe("started")
    })
    const body = JSON.parse(fetchMock.mock.calls[2][1]?.body as string)
    expect(body).toMatchObject({
      file_ids: ["a"],
      profile: "detailed",
      max_workers: 3,
      image_provider: "gemini",
    })
    expect(result.current.held?.sent).toEqual(["a"])
    expect(result.current.held?.cleared).toEqual(["c"])
    expect(result.current.held?.held.map((x) => x.file_id)).toContain("b")
    await act(async () => {
      await result.current.processAdmitted("a")
    })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
  it.each(["refused", "future"])(
    "does not process a %s 200 response",
    async (outcome) => {
      route()
      const { result } = setup()
      await act(async () => {
        await result.current.start(request)
      })
      fetchMock.mockResolvedValueOnce(json(answer("a", outcome)))
      await act(async () => {
        await result.current.recordAdmission("a", "Reviewed")
      })
      await act(async () => {
        expect(await result.current.processAdmitted("a")).toBe("failed")
      })
      expect(fetchMock).toHaveBeenCalledTimes(2)
    }
  )
  it("handles nothing_to_override without appending or claiming a decision", async () => {
    route()
    const { result, client } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    fetchMock.mockResolvedValueOnce(json(answer("a", "nothing_to_override")))
    await act(async () => {
      await result.current.recordAdmission("a", "Reviewed")
    })
    expect(result.current.held?.admissions?.a.canProcess).toBe(true)
    expect(
      client.getQueryState(["financial-decisions", "case-1"])?.isInvalidated
    ).toBe(false)
  })
  it("retains a server hold that arrives when releasing previously cleared files", async () => {
    route()
    const { result } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    fetchMock.mockResolvedValueOnce(blocked("c"))
    await act(async () => {
      expect(await result.current.release()).toBe(0)
    })
    expect(result.current.held?.held.map((x) => x.file_id)).toEqual([
      "a",
      "b",
      "c",
    ])
    expect(result.current.held?.cleared).toEqual([])
    expect(toast.error).not.toHaveBeenCalled()
  })
  it("renders a server hold after the preliminary check cleared every file", async () => {
    route([file("a", "not_native")])
    fetchMock.mockResolvedValueOnce(blocked("a"))
    const { result } = setup()
    await act(async () => {
      expect(await result.current.start({ fileIds: ["a"] })).toBe("held")
    })
    expect(result.current.held?.held[0].claimants).toEqual(["bai2", "mt940"])
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it("replaces a stale admission with the new server finding without losing other held files", async () => {
    route()
    const { result } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    fetchMock.mockResolvedValueOnce(json(answer()))
    await act(async () => {
      await result.current.recordAdmission("a", "Reviewed")
    })
    fetchMock.mockResolvedValueOnce(blocked("a"))
    await act(async () => {
      expect(await result.current.processAdmitted("a")).toBe("held")
    })
    expect(result.current.held?.admissions?.a).toBeUndefined()
    expect(result.current.held?.held.map((x) => x.file_id).sort()).toEqual([
      "a",
      "b",
    ])
  })
  it("does not repeat the admission when a processing request fails", async () => {
    route()
    const { result } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    fetchMock.mockResolvedValueOnce(json(answer()))
    await act(async () => {
      await result.current.recordAdmission("a", "Reviewed")
    })
    fetchMock.mockRejectedValueOnce(new Error("offline"))
    await act(async () => {
      await result.current.processAdmitted("a")
    })
    expect(result.current.held?.admissions?.a.canProcess).toBe(true)
    fetchMock.mockResolvedValueOnce(json({ task_id: "retry" }))
    await act(async () => {
      await result.current.processAdmitted("a")
    })
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/admit?"))
    ).toHaveLength(1)
  })
  it("blocks duplicate submissions, dismiss and processing while a decision is pending", async () => {
    route()
    const { result } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    let resolve!: (value: Response) => void
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    let pending!: Promise<void>
    act(() => {
      pending = result.current.recordAdmission("a", "Reviewed")
      void result.current.recordAdmission("a", "Again")
      result.current.dismiss()
    })
    expect(result.current.isBusy).toBe(true)
    expect(result.current.held).not.toBeNull()
    await act(async () => {
      expect(await result.current.processAdmitted("b")).toBe("failed")
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await act(async () => {
      resolve(json(answer()))
      await pending
    })
    expect(result.current.isBusy).toBe(false)
  })
  it("keeps an uncertain admission visible without sending or retrying it", async () => {
    route()
    const { result } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    fetchMock.mockRejectedValueOnce(new Error("connection lost"))
    await act(async () => {
      await result.current.recordAdmission("a", "Reviewed")
    })
    expect(result.current.held?.admissionErrors?.a).toContain(
      "Check the decision history"
    )
    expect(result.current.held?.admissions?.a).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it("does not carry a pending decision into another case", async () => {
    route()
    const { result, rerender } = setup()
    await act(async () => {
      await result.current.start(request)
    })
    let resolve!: (value: Response) => void
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    let pending!: Promise<void>
    act(() => {
      pending = result.current.recordAdmission("a", "Reviewed")
    })
    rerender({ caseId: "case-2" })
    expect(result.current.held).toBeNull()
    await act(async () => {
      resolve(json(answer()))
      await pending
    })
    expect(result.current.held).toBeNull()
    await act(async () => {
      await result.current.processAdmitted("a")
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

it("uses the original case if navigation occurs while the preliminary check is pending", async () => {
  const { result, rerender } = setup()
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  let pending!: Promise<unknown>
  act(() => {
    pending = result.current.start({ fileIds: ["a"] })
  })
  rerender({ caseId: "case-2" })
  fetchMock.mockResolvedValueOnce(json({ task_id: "original-case-task" }))
  await act(async () => {
    resolve(
      json({
        case_id: "case-1",
        files: [file("a", "not_native")],
        summary: null,
      })
    )
    await pending
  })
  expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string).case_id).toBe(
    "case-1"
  )
  expect(result.current.held).toBeNull()
})

it("updates the displayed file finding when admission rechecks the bytes", async () => {
  route()
  const { result } = setup()
  await act(async () => {
    await result.current.start(request)
  })
  fetchMock.mockResolvedValueOnce(
    json({
      ...answer(),
      route_outcome: "native",
      detected_format: "bai2",
      claimants: ["bai2"],
    })
  )
  await act(async () => {
    await result.current.recordAdmission("a", "Reviewed")
  })
  expect(
    result.current.held?.held.find((f) => f.file_id === "a")
  ).toMatchObject({ outcome: "native", detected_format: "bai2" })
})

it("does not offer admission to an unexpected file named by a server refusal", async () => {
  route([file("a", "not_native")])
  fetchMock.mockResolvedValueOnce(blocked("other-file"))
  const { result } = setup()
  await act(async () => {
    expect(await result.current.start({ fileIds: ["a"] })).toBe("failed")
  })
  expect(result.current.held).toBeNull()
  expect(toast.error).toHaveBeenCalled()
})

it("does not choose the first of contradictory repeated file checks", async () => {
  route([file("a", "not_native"), file("a", "native")])
  const { result } = setup()
  await act(async () => {
    expect(await result.current.start({ fileIds: ["a"] })).toBe("held")
  })
  expect(result.current.held?.checkError).toContain("repeated an identifier")
  expect(result.current.held?.cleared).toEqual([])
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
