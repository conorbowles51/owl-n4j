import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

let clock = 0
const success = vi.fn()
vi.mock("sonner", () => ({ toast: { success: (m: string) => success(m), error: vi.fn() } }))
vi.mock("@/features/cases/hooks/use-snapshots", () => ({
  useCreateSnapshot: () => ({
    isPending: false,
    mutate: (_body: unknown, opts: { onSuccess: (s: unknown) => void }) =>
      opts.onSuccess({ node_count: 2, link_count: 1, timeline_count: 1 }),
  }),
}))
vi.mock("../lib/graph-snapshot", () => ({
  readCanvasGraph: () => null,
  // Reading the canvas takes three seconds on this fake clock.
  buildSnapshotSubgraph: () => {
    clock += 3000
    return { nodes: [], links: [], positions: "none" }
  },
}))

import { SaveSnapshotDialog } from "./SaveSnapshotDialog"

afterEach(() => vi.restoreAllMocks())

describe("SaveSnapshotDialog", () => {
  it("reports the seconds from the click, including reading the canvas", () => {
    vi.spyOn(performance, "now").mockImplementation(() => clock)
    render(
      <SaveSnapshotDialog
        caseId="c1"
        shown={{ nodes: [{ key: "a", label: "A", type: "Person", properties: {} }], edges: [] } as never}
        open
        onOpenChange={() => {}}
      />,
    )
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "s" } })
    fireEvent.click(screen.getByRole("button", { name: /Save snapshot/ }))
    expect(success).toHaveBeenCalledWith("Snapshot saved: 2 entities, 1 links, 1 events (3.0 s)")
  })
})
