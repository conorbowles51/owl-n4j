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
    error: null,
    startScan: vi.fn(),
    cancel: vi.fn(),
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
})
