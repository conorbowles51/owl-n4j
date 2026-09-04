import { render } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { EvidenceExplorer } from "./EvidenceExplorer"

const mocks = vi.hoisted(() => ({
  resetForCase: vi.fn(),
  openDetail: vi.fn(),
}))

vi.mock("../evidence.store", () => {
  const state = {
    currentFolderId: null,
    selectedFileIds: new Set<string>(),
    clearSelection: vi.fn(),
    resetForCase: mocks.resetForCase,
    openDetail: mocks.openDetail,
  }
  return {
    useEvidenceStore: (selector?: (value: typeof state) => unknown) =>
      selector ? selector(state) : state,
  }
})
vi.mock("../hooks/use-folder-mutations", () => ({
  useCreateFolder: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteFolder: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock("../hooks/use-evidence-detail", () => ({
  useDeleteEvidence: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock("./FolderTreeSidebar", () => ({ FolderTreeSidebar: () => <div /> }))
vi.mock("./FileListPanel", () => ({ FileListPanel: () => <div /> }))
vi.mock("./CreateFolderDialog", () => ({ CreateFolderDialog: () => null }))
vi.mock("./DeleteFolderDialog", () => ({ DeleteFolderDialog: () => null }))
vi.mock("./DeleteEvidenceDialog", () => ({ DeleteEvidenceDialog: () => null }))
vi.mock("./FolderContextDialog", () => ({ FolderContextDialog: () => null }))
vi.mock("./CaseProcessingProfileDialog", () => ({ CaseProcessingProfileDialog: () => null }))
vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}))

describe("Evidence citation deep links", () => {
  beforeEach(() => {
    mocks.resetForCase.mockReset()
    mocks.openDetail.mockReset()
  })

  it("opens the cited file with page and transcript anchors", () => {
    render(
      <MemoryRouter initialEntries={["/cases/case-1/evidence?file=evidence-7&page=4&start_seconds=12.5&end_seconds=18&start_char=90"]}>
        <Routes>
          <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(mocks.resetForCase).toHaveBeenCalledWith("case-1")
    expect(mocks.openDetail).toHaveBeenCalledWith("evidence-7", {
      page: 4,
      startSeconds: 12.5,
      endSeconds: 18,
      startChar: 90,
    })
  })
})
