import { render, waitFor } from "@testing-library/react"
import { foldersAPI } from "../folders.api"
import { toast } from "sonner"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { EvidenceExplorer } from "./EvidenceExplorer"

const mocks = vi.hoisted(() => ({
  resetForCase: vi.fn(),
  openDetail: vi.fn(),
  revealFile: vi.fn(),
  queryClient: { invalidateQueries: vi.fn() },
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => mocks.queryClient,
}))

vi.mock("../evidence.store", () => {
  const state = {
    sortBy: "name", sortDirection: "asc",
    currentFolderId: null,
    selectedFileIds: new Set<string>(),
    clearSelection: vi.fn(),
    resetForCase: mocks.resetForCase,
    openDetail: mocks.openDetail,
    revealFile: mocks.revealFile,
  }
  return {
    useEvidenceStore: Object.assign((selector?: (value: typeof state) => unknown) => selector ? selector(state) : state, { getState: () => state }),
  }
})
vi.mock("../hooks/use-folder-mutations", () => ({
  useCreateFolder: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteFolder: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock("../hooks/use-evidence-detail", () => ({
  useDeleteEvidence: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock("./EvidenceMoveProvider", () => ({ EvidenceMoveProvider: ({ children }: { children: React.ReactNode }) => children }))
vi.mock("./FolderTreeSidebar", () => ({ FolderTreeSidebar: () => <div /> }))
vi.mock("./FileListPanel", () => ({ FileListPanel: () => <div /> }))
vi.mock("./CreateFolderDialog", () => ({ CreateFolderDialog: () => null }))
vi.mock("./DeleteFolderDialog", () => ({ DeleteFolderDialog: () => null }))
vi.mock("./DeleteEvidenceDialog", () => ({ DeleteEvidenceDialog: () => null }))
vi.mock("./FolderContextDialog", () => ({ FolderContextDialog: () => null }))
vi.mock("./CaseProcessingProfileDialog", () => ({
  CaseProcessingProfileDialog: () => null,
}))
vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizablePanel: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizableHandle: () => <div />,
}))

describe("Evidence citation deep links", () => {
  beforeEach(() => {
    mocks.resetForCase.mockReset()
    mocks.openDetail.mockReset()
    mocks.revealFile.mockReset()
    vi.restoreAllMocks()
  })

  it("opens the cited file with page and transcript anchors", () => {
    render(
      <MemoryRouter
        initialEntries={[
          "/cases/case-1/evidence?file=evidence-7&page=4&start_seconds=12.5&end_seconds=18&start_char=90",
        ]}
      >
        <Routes>
          <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
        </Routes>
      </MemoryRouter>
    )
    expect(mocks.resetForCase).toHaveBeenCalledWith("case-1")
    expect(mocks.openDetail).toHaveBeenCalledWith("evidence-7", {
      page: 4,
      startSeconds: 12.5,
      endSeconds: 18,
      startChar: 90,
    })
  })

  it("resolves reveal links without opening the document preview", async () => {
    const target = {
      file_id: "file-1",
      folder_id: "child",
      ancestor_ids: ["parent", "child"],
      file_offset: 500,
      file_limit: 250,
    }
    vi.spyOn(foldersAPI, "getFileLocation").mockResolvedValue(target)
    render(
      <MemoryRouter
        initialEntries={["/cases/case-1/evidence?file=file-1&reveal=1"]}
      >
        <Routes>
          <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
        </Routes>
      </MemoryRouter>
    )
    await waitFor(() => expect(mocks.revealFile).toHaveBeenCalledWith(target))
    expect(mocks.openDetail).not.toHaveBeenCalled()
  })

  it("reports unavailable files without changing the current folder", async () => {
    vi.spyOn(foldersAPI, "getFileLocation").mockRejectedValue(
      new Error("Not found")
    )
    const error = vi.spyOn(toast, "error")
    render(
      <MemoryRouter
        initialEntries={["/cases/case-1/evidence?file=deleted&reveal=1"]}
      >
        <Routes>
          <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
        </Routes>
      </MemoryRouter>
    )
    await waitFor(() => expect(error).toHaveBeenCalled())
    expect(mocks.revealFile).not.toHaveBeenCalled()
  })

  it("ignores a location response after leaving the case", async () => {
    let resolve!: (
      value: Awaited<ReturnType<typeof foldersAPI.getFileLocation>>
    ) => void
    const lookup = vi.spyOn(foldersAPI, "getFileLocation").mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const view = render(
      <MemoryRouter
        initialEntries={["/cases/case-1/evidence?file=file-1&reveal=1"]}
      >
        <Routes>
          <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
        </Routes>
      </MemoryRouter>
    )
    view.unmount()
    expect(lookup.mock.calls[0][2]?.aborted).toBe(true)
    resolve({
      file_id: "file-1",
      folder_id: null,
      ancestor_ids: [],
      file_offset: 0,
      file_limit: 250,
    })
    await Promise.resolve()
    expect(mocks.revealFile).not.toHaveBeenCalled()
  })
})
