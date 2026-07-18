import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { graphAPI } from "../api"
import { useLocationCorrection } from "./use-location-correction"

vi.mock("../api", () => ({
  graphAPI: {
    geocodeNode: vi.fn(),
    undoLocationCorrection: vi.fn(),
  },
}))

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

describe("useLocationCorrection", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.mocked(graphAPI.geocodeNode).mockReset()
    vi.mocked(graphAPI.undoLocationCorrection).mockReset()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
  })

  it("previews without applying", async () => {
    vi.mocked(graphAPI.geocodeNode).mockResolvedValue({
      success: true,
      latitude: 51.5,
      longitude: -0.12,
      formatted_address: "London, UK",
      confidence: "high",
      applied: false,
    })

    const { result } = renderHook(
      () =>
        useLocationCorrection({
          caseId: "case-1",
          nodeKey: "loc-1",
          sourceView: "map_popup",
        }),
      { wrapper: createWrapper(queryClient) }
    )

    await act(async () => {
      await result.current.preview("London")
    })

    expect(graphAPI.geocodeNode).toHaveBeenCalledWith(
      "loc-1",
      "case-1",
      "London",
      false,
      "map_popup"
    )
  })

  it("applies and invalidates graph and map data", async () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries")
    const onApplied = vi.fn()
    vi.mocked(graphAPI.geocodeNode).mockResolvedValue({
      success: true,
      latitude: 51.5,
      longitude: -0.12,
      formatted_address: "London, UK",
      confidence: "manual",
      geocoder_confidence: "high",
      applied: true,
    })

    const { result } = renderHook(
      () =>
        useLocationCorrection({
          caseId: "case-1",
          nodeKey: "loc-1",
          sourceView: "evidence_panel",
          extraInvalidateKeys: [["evidence-file-entities", "file-1"]],
          onApplied,
        }),
      { wrapper: createWrapper(queryClient) }
    )

    await act(async () => {
      await result.current.apply("London")
    })

    await waitFor(() => expect(onApplied).toHaveBeenCalled())
    expect(graphAPI.geocodeNode).toHaveBeenCalledWith(
      "loc-1",
      "case-1",
      "London",
      true,
      "evidence_panel"
    )
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["map", "case-1"] })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["evidence-file-entities", "file-1"],
    })
  })

  it("undoes through the geocode undo endpoint", async () => {
    const onUndone = vi.fn()
    vi.mocked(graphAPI.undoLocationCorrection).mockResolvedValue({
      success: true,
      latitude: 1,
      longitude: 2,
      formatted_address: "Old",
      confidence: "low",
    })

    const { result } = renderHook(
      () =>
        useLocationCorrection({
          caseId: "case-1",
          nodeKey: "loc-1",
          sourceView: "entity_detail",
          onUndone,
        }),
      { wrapper: createWrapper(queryClient) }
    )

    await act(async () => {
      await result.current.undo()
    })

    await waitFor(() => expect(onUndone).toHaveBeenCalled())
    expect(graphAPI.undoLocationCorrection).toHaveBeenCalledWith(
      "loc-1",
      "case-1",
      "entity_detail"
    )
  })
})
