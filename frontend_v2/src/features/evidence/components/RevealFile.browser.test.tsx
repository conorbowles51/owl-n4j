import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
  act,
} from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { useUIStore } from "@/stores/ui.store"
import type { EvidenceFileRecord } from "@/types/evidence.types"
import { foldersAPI } from "../folders.api"
import { useEvidenceStore } from "../evidence.store"
import { EvidenceExplorer } from "./EvidenceExplorer"
import "@/styles/globals.css"

vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({
    objectUrl:
      "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
    loading: false,
    error: null,
  }),
  openProtectedFile: vi.fn(),
}))
vi.mock("../hooks/use-folder-mutations", () => ({
  useCreateFolder: () => ({ mutate: vi.fn() }),
  useDeleteFolder: () => ({ mutate: vi.fn() }),
}))
vi.mock("../hooks/use-evidence-detail", () => ({
  useDeleteEvidence: () => ({ mutate: vi.fn() }),
  useProcessBackground: () => ({ mutate: vi.fn() }),
}))
vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: {} }),
}))
vi.mock("@/features/cases/hooks/use-case-permissions", () => ({
  useCasePermissions: () => ({ canEdit: false }),
}))
vi.mock("@/features/workspace/hooks/use-workspace", () => ({
  usePinStatus: () => ({ data: {} }),
  usePinItem: () => ({ mutate: vi.fn() }),
  useBulkPinItems: () => ({ mutate: vi.fn() }),
  useUnpinItem: () => ({ mutate: vi.fn() }),
}))
vi.mock("./FolderTreeSidebar", () => ({
  FolderTreeSidebar: () => <nav aria-label="Folder tree" />,
}))
vi.mock("./FileListToolbar", () => ({ FileListToolbar: () => null }))
vi.mock("./InlineDropZone", () => ({ InlineDropZone: () => null }))
vi.mock("./CreateFolderDialog", () => ({ CreateFolderDialog: () => null }))
vi.mock("./DeleteFolderDialog", () => ({ DeleteFolderDialog: () => null }))
vi.mock("./DeleteEvidenceDialog", () => ({ DeleteEvidenceDialog: () => null }))
vi.mock("./FolderContextDialog", () => ({ FolderContextDialog: () => null }))
vi.mock("./CaseProcessingProfileDialog", () => ({
  CaseProcessingProfileDialog: () => null,
}))
vi.mock("@/features/dossiers/components/AddEvidenceToDossierDialog", () => ({
  AddEvidenceToDossierDialog: () => null,
}))

const file = (id: string, folderId: string | null): EvidenceFileRecord => ({
  id,
  case_id: "case-1",
  folder_id: folderId,
  original_filename: `${id}.png`,
  stored_path: `/fixtures/${id}.png`,
  size: 100,
  sha256: "a".repeat(64),
  status: "processed",
  processing_stale: false,
  is_duplicate: false,
  duplicate_of: null,
  is_relevant: true,
  owner: null,
  created_at: null,
  processed_at: null,
  last_error: null,
  legacy_id: null,
  summary: null,
  transcription: null,
  transcription_segments: [],
  transcription_speakers: {},
  transcription_speaker_merges: {},
  entity_count: 0,
  relationship_count: 0,
  last_processed_folder_id: null,
})

function Viewer({ evidenceId = "target" }: { evidenceId?: string }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <button onClick={() => setOpen(true)}>Reopen source</button>
      <DocumentViewer
        open={open}
        onOpenChange={setOpen}
        caseId="case-1"
        evidenceId={evidenceId}
        documentName="target.png"
        documentUrl="/fixtures/target.png"
      />
    </>
  )
}

function mount(initialEntry = "/cases/case-1/chat") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Viewer />
        <div style={{ height: 450, width: 1000, maxWidth: "100%" }}>
          <Routes>
            <Route path="/cases/:id/chat" element={<div>Chat source</div>} />
            <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
          </Routes>
        </div>
      </MemoryRouter>
    </QueryClientProvider>
  )
  return client
}

describe("open file location in Chromium", () => {
  beforeEach(async () => {
    await page.viewport(1280, 800)
    vi.restoreAllMocks()
    useEvidenceStore.getState().resetForCase(crypto.randomUUID())
    useEvidenceStore.getState().resetForCase("case-1")
    useUIStore.getState().setGraphPanelCollapsed(true)
  })
  afterEach(cleanup)

  it("closes the viewer, reveals the correct page, scrolls and focuses the file, and can repeat on the same URL", async () => {
    const store = useEvidenceStore.getState()
    store.setCurrentFolder("old-folder")
    store.setFileSearchTerm("hidden")
    store.setStatusFilter("failed")
    store.setTypeFilter("audio")
    store.openDetail("old", { page: 4 })
    const locate = vi.spyOn(foldersAPI, "getFileLocation").mockResolvedValue({
      file_id: "target",
      folder_id: "child",
      ancestor_ids: ["parent"],
      file_offset: 250,
      file_limit: 250,
    })
    const contents = vi
      .spyOn(foldersAPI, "getContents")
      .mockImplementation(async (_caseId, folderId, params) => ({
        folder: folderId
          ? {
              id: folderId,
              name: "Child folder",
              parent_id: "parent",
              has_profile: false,
            }
          : null,
        breadcrumbs: folderId ? [{ id: "parent", name: "Parent folder" }] : [],
        folders: [],
        files:
          folderId === "child" && params?.offset === 250
            ? [
                ...Array.from({ length: 30 }, (_, index) =>
                  file(`sibling-${index}`, folderId)
                ),
                file("target", folderId),
              ]
            : [],
        file_total: 281,
        file_limit: 250,
        file_offset: params?.offset ?? 0,
      }))
    const client = mount()
    const link = await screen.findByRole("link", { name: "Open file location" })
    expect(link).toHaveAttribute(
      "href",
      "/cases/case-1/evidence?file=target&reveal=1"
    )
    await page.screenshot({
      path: "../../../../../output/playwright/open-file-location-viewer.png",
    })
    await act(async () => {
      await page.getByRole("link", { name: "Open file location" }).click()
    })
    const target = await screen.findByRole("button", { name: "target.png" })
    const row = target.closest("tr")!
    await waitFor(() => expect(row).toHaveFocus())
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByText("2 / 2")).toBeVisible()
    expect(screen.getByText("Parent folder")).toBeVisible()
    expect(row).toHaveClass("bg-primary/10")
    const bounds = row.getBoundingClientRect()
    const viewport = row.closest(".overflow-auto")!.getBoundingClientRect()
    expect(bounds.top).toBeGreaterThanOrEqual(viewport.top)
    expect(bounds.bottom).toBeLessThanOrEqual(viewport.bottom + 1)
    expect(bounds.bottom).toBeLessThanOrEqual(window.innerHeight)
    expect(row.closest(".overflow-auto")!.scrollTop).toBeGreaterThan(0)
    expect(useEvidenceStore.getState()).toMatchObject({
      currentFolderId: "child",
      filePage: 1,
      detailFileId: "target",
      detailAnchor: null,
      revealTargetFileId: null,
      fileSearchTerm: "",
      statusFilter: "all",
      typeFilter: "",
    })
    expect([...useEvidenceStore.getState().expandedFolderIds]).toEqual([
      "parent",
      "child",
    ])
    expect(useEvidenceStore.getState().selectedFileIds.size).toBe(0)
    expect(contents).toHaveBeenCalledWith(
      "case-1",
      "child",
      expect.objectContaining({
        offset: 250,
        status: undefined,
        type: undefined,
      }),
      expect.any(AbortSignal),
    )
    await page.screenshot({
      path: "../../../../../output/playwright/open-file-location-revealed.png",
    })

    // Reusing the same link must resolve again, including a file moved since the preview opened.
    locate.mockResolvedValue({
      file_id: "target",
      folder_id: null,
      ancestor_ids: [],
      file_offset: 0,
      file_limit: 250,
    })
    contents.mockResolvedValue({
      folder: null,
      breadcrumbs: [],
      folders: [],
      files: [file("target", null)],
      file_total: 1,
      file_limit: 250,
      file_offset: 0,
    })
    fireEvent.click(screen.getByRole("button", { name: "Reopen source" }))
    fireEvent.click(
      await screen.findByRole("link", { name: "Open file location" })
    )
    await waitFor(() => expect(locate).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(useEvidenceStore.getState().currentFolderId).toBeNull()
    )
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "target.png" }).closest("tr")
      ).toHaveFocus()
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    cleanup()
    client.clear()
  })

  it("does not offer a location for previews without an evidence record", () => {
    render(
      <MemoryRouter>
        <DocumentViewer
          open
          onOpenChange={vi.fn()}
          documentName="external.png"
          documentUrl="/external.png"
        />
      </MemoryRouter>
    )
    expect(
      screen.queryByRole("link", { name: "Open file location" })
    ).not.toBeInTheDocument()
  })

  it("keeps the containing folder visible on a narrow screen", async () => {
    await page.viewport(390, 844)
    vi.spyOn(foldersAPI, "getFileLocation").mockResolvedValue({
      file_id: "target",
      folder_id: null,
      ancestor_ids: [],
      file_offset: 0,
      file_limit: 250,
    })
    vi.spyOn(foldersAPI, "getContents").mockResolvedValue({
      folder: null,
      breadcrumbs: [],
      folders: [],
      files: [file("target", null)],
      file_total: 1,
      file_limit: 250,
      file_offset: 0,
    })
    const client = mount()
    const link = await screen.findByRole("link", { name: "Open file location" })
    const bounds = link.getBoundingClientRect()
    expect(bounds.left).toBeGreaterThanOrEqual(0)
    expect(bounds.right).toBeLessThanOrEqual(390)
    await act(async () => {
      await page.getByRole("link", { name: "Open file location" }).click()
    })
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "target.png" }).closest("tr")
      ).toHaveFocus()
    )
    expect(useUIStore.getState().graphPanelCollapsed).toBe(true)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    cleanup()
    client.clear()
  })
})
