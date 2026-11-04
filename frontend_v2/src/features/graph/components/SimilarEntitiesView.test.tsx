import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SimilarEntitiesView } from "./SimilarEntitiesView"
import type { GraphData } from "@/types/graph.types"

const graphMocks = vi.hoisted(() => ({
  trackerOptions: null as null | {
    onCompleted?: () => void
    onPartial?: () => void
  },
  latestDialogProps: null as null | { open: boolean },
  setDialogOpen: vi.fn(),
  startTracking: vi.fn(),
  clearJob: vi.fn(),
  rejectMergePair: vi.fn(),
  startScan: vi.fn(),
  removePair: vi.fn(),
  summary: null as null | { total: number; belowThreshold: number; threshold: number; floor: number },
}))

vi.mock("../hooks/use-similar-entities", () => ({
  useSimilarEntities: () => ({
    isScanning: false,
    progress: null,
    currentType: null,
    results: [
      {
        key1: "entity-a",
        name1: "Alpha",
        type1: "person",
        key2: "entity-b",
        name2: "Alpha Inc",
        type2: "organization",
        similarity: 0.91,
      },
    ],
    summary: graphMocks.summary,
    error: null,
    startScan: graphMocks.startScan,
    cancel: vi.fn(),
    removePair: graphMocks.removePair,
  }),
}))

vi.mock("../hooks/use-graph-data", () => ({
  useEntityTypes: () => ({ data: { entity_types: [] } }),
}))

vi.mock("../hooks/use-merge-tracker", () => ({
  useMergeTracker: (options: { onCompleted?: () => void; onPartial?: () => void }) => {
    graphMocks.trackerOptions = options
    return {
      activeJob: null,
      startTracking: graphMocks.startTracking,
      clearJob: graphMocks.clearJob,
      setDialogOpen: graphMocks.setDialogOpen,
    }
  },
}))

vi.mock("../api", () => ({
  graphAPI: {
    rejectMergePair: graphMocks.rejectMergePair,
  },
}))

vi.mock("./MergeEntitiesDialog", () => ({
  MergeEntitiesDialog: (props: { open: boolean }) => {
    graphMocks.latestDialogProps = props
    return <div data-testid="merge-dialog" data-open={String(props.open)} />
  },
}))

vi.mock("./EntityComparisonDialog", () => ({
  EntityComparisonDialog: () => null,
}))

const graphData: GraphData = {
  nodes: [
    { key: "entity-a", label: "Alpha", type: "person", properties: {} },
    { key: "entity-b", label: "Alpha Inc", type: "organization", properties: {} },
  ],
  edges: [],
}

describe("SimilarEntitiesView", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    )
    graphMocks.trackerOptions = null
    graphMocks.latestDialogProps = null
    graphMocks.setDialogOpen.mockReset()
    graphMocks.startTracking.mockReset()
    graphMocks.clearJob.mockReset()
    graphMocks.rejectMergePair.mockReset()
    graphMocks.startScan.mockReset()
    graphMocks.removePair.mockReset()
    graphMocks.summary = null
  })

  it("states what the scan found against what is shown and what the threshold leaves unlisted", () => {
    graphMocks.summary = { total: 1500, belowThreshold: 320, threshold: 0.7, floor: 0.5 }
    render(<SimilarEntitiesView caseId="case-1" graphData={graphData} onRefresh={vi.fn()} />)
    const line = screen.getByTestId("similar-scan-summary")
    expect(line).toHaveTextContent("Showing 1 of 1,500 pairs found, most alike first.")
    expect(line).toHaveTextContent("320 more pairs are 50% to under 70% alike: counted, not listed")
  })

  it("adds no summary line when everything found is shown", () => {
    graphMocks.summary = { total: 1, belowThreshold: 0, threshold: 0.7, floor: 0.5 }
    render(<SimilarEntitiesView caseId="case-1" graphData={graphData} onRefresh={vi.fn()} />)
    expect(screen.queryByTestId("similar-scan-summary")).toBeNull()
  })

  it("removes a pair from the list once the server records it as not a duplicate", async () => {
    graphMocks.rejectMergePair.mockResolvedValue({ id: "r-1" })
    render(<SimilarEntitiesView caseId="case-1" graphData={graphData} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByRole("button", { name: /not a duplicate/i }))

    await waitFor(() => expect(graphMocks.removePair).toHaveBeenCalledWith("entity-a", "entity-b"))
    expect(graphMocks.rejectMergePair).toHaveBeenCalledWith("case-1", "entity-a", "entity-b")
  })

  it("keeps the pair and says so when the server refuses", async () => {
    graphMocks.rejectMergePair.mockRejectedValue(new Error("Not Found"))
    render(<SimilarEntitiesView caseId="case-1" graphData={graphData} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByRole("button", { name: /not a duplicate/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not mark Alpha and Alpha Inc as not duplicates: Not Found"
    )
    expect(graphMocks.removePair).not.toHaveBeenCalled()
  })

  it("refreshes on completed merge without closing the dialog directly", async () => {
    const onRefresh = vi.fn()

    render(
      <SimilarEntitiesView
        caseId="case-1"
        graphData={graphData}
        onRefresh={onRefresh}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /merge/i }))

    expect(graphMocks.latestDialogProps?.open).toBe(true)

    act(() => {
      graphMocks.trackerOptions?.onCompleted?.()
    })

    expect(onRefresh).toHaveBeenCalledTimes(1)
    await waitFor(() => {
      expect(graphMocks.latestDialogProps?.open).toBe(true)
    })
  })

  it("deselects all types before selecting one for the duplicate scan", () => {
    render(
      <SimilarEntitiesView
        caseId="case-1"
        graphData={graphData}
        onRefresh={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /^Types$/ }))
    fireEvent.click(screen.getByRole("button", { name: "Deselect All" }))

    expect(screen.getByRole("button", { name: /^Scan$/ })).toBeDisabled()

    fireEvent.click(screen.getByRole("checkbox", { name: /organization/i }))
    fireEvent.click(screen.getByRole("button", { name: /^Scan$/ }))

    expect(graphMocks.startScan).toHaveBeenCalledWith({
      entityTypes: ["organization"],
      similarityThreshold: 0.7,
    })
  })
})
