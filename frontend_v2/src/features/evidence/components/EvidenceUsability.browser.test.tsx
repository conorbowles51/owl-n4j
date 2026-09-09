import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { page, userEvent } from "vitest/browser"
import { EvidenceExplorer } from "./EvidenceExplorer"
import { foldersAPI, type FolderContentsParams } from "../folders.api"
import { useEvidenceStore } from "../evidence.store"
import { EVIDENCE_DRAG_TYPE } from "../hooks/use-evidence-moves"
import type {
  EvidenceFileRecord,
  EvidenceFolder,
  FolderTreeNode,
} from "@/types/evidence.types"
import "@/styles/globals.css"

const mocks = vi.hoisted(() => ({ upload: vi.fn(), canEdit: true }))
vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: {} }),
}))
vi.mock("@/features/cases/hooks/use-case-permissions", () => ({
  useCasePermissions: () => ({
    canEdit: mocks.canEdit,
    canUploadEvidence: mocks.canEdit,
  }),
}))
vi.mock("../hooks/use-case-processing-profile", () => ({
  useCaseProcessingProfile: () => ({ data: {} }),
}))
vi.mock("../hooks/use-jobs", () => ({ useJobs: () => ({ data: [] }) }))
vi.mock("../hooks/use-upload-to-folder", () => ({
  useUploadToFolder: () => ({ mutate: mocks.upload }),
}))
vi.mock("../hooks/use-evidence-detail", () => ({
  useDeleteEvidence: () => ({ mutate: vi.fn() }),
  useProcessBackground: () => ({ mutate: vi.fn() }),
}))
vi.mock("@/features/workspace/hooks/use-workspace", () => ({
  usePinStatus: () => ({ data: {} }),
  usePinItem: () => ({ mutate: vi.fn() }),
  useBulkPinItems: () => ({ mutate: vi.fn() }),
  useUnpinItem: () => ({ mutate: vi.fn() }),
}))
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

const longName =
  "Alpha - investigation correspondence and transaction records with supporting exhibits - September 2026.pdf"
let files: EvidenceFileRecord[]
let folders: EvidenceFolder[]
let client: QueryClient
const record = (
  id: string,
  name: string,
  folder_id: string | null = null
): EvidenceFileRecord =>
  ({
    id,
    case_id: "case",
    original_filename: name,
    folder_id,
    status: "processed",
    processing_stale: true,
    size: 2400,
    created_at: id === "a" ? "2026-09-01" : "2026-09-06",
    entity_count: 4,
  }) as EvidenceFileRecord
const folder = (
  id: string,
  name: string,
  parent_id: string | null = null
): EvidenceFolder =>
  ({
    id,
    name,
    parent_id,
    created_at: "2026-09-01",
    updated_at: null,
    file_count: 1,
    subfolder_count: 0,
    has_profile: false,
  }) as EvidenceFolder
function path(id: string | null): { id: string; name: string }[] {
  const found = folders.find((folder) => folder.id === id)
  return found
    ? [...path(found.parent_id), { id: found.id, name: found.name }]
    : []
}
function sorted(rows: EvidenceFileRecord[], params: FolderContentsParams = {}) {
  return [...rows].sort((a, b) => {
    const av =
      params.sort_by === "date"
        ? (a.created_at ?? "")
        : a.original_filename.toLowerCase()
    const bv =
      params.sort_by === "date"
        ? (b.created_at ?? "")
        : b.original_filename.toLowerCase()
    return (
      av.localeCompare(bv) * (params.sort_direction === "desc" ? -1 : 1) ||
      a.id.localeCompare(b.id)
    )
  })
}
function seed() {
  files = [
    record("a", longName),
    record("b", "Zulu.pdf"),
    record("nested", "Report_100%.pdf", "child"),
  ]
  folders = [
    folder("archive", "Archive"),
    folder("parent", "Statements"),
    folder("child", "September", "parent"),
  ]
  vi.spyOn(foldersAPI, "getTree").mockImplementation(async () => {
    const build = (parent: string | null): FolderTreeNode[] =>
      folders
        .filter((f) => f.parent_id === parent)
        .map((f) => ({ ...f, children: build(f.id) }))
    return build(null)
  })
  vi.spyOn(foldersAPI, "getContents").mockImplementation(
    async (_case, folderId, params = {}) => {
      const matches = sorted(
        files.filter((file) => file.folder_id === folderId),
        params
      )
      const current = folders.find((folder) => folder.id === folderId)
      return {
        folder: current ?? null,
        breadcrumbs: path(current?.parent_id ?? null),
        folders: folders.filter((folder) => folder.parent_id === folderId),
        files: matches.slice(params.offset ?? 0, (params.offset ?? 0) + 250),
        file_total: matches.length,
        file_limit: 250,
        file_offset: params.offset ?? 0,
      }
    }
  )
  vi.spyOn(foldersAPI, "search").mockImplementation(
    async (_case, query, scope, folderId, params) => {
      const matches = sorted(
        files.filter(
          (file) =>
            file.original_filename
              .toLowerCase()
              .includes(query.toLowerCase()) &&
            (scope === "case" ||
              folderId === null ||
              path(file.folder_id).some((folder) => folder.id === folderId))
        ),
        params
      )
      return {
        files: matches.map((file) => ({
          ...file,
          folder_path: path(file.folder_id),
        })),
        file_total: matches.length,
        file_limit: 250,
        file_offset: 0,
      }
    }
  )
  vi.spyOn(foldersAPI, "getFileLocation").mockImplementation(
    async (_case, id) => {
      const file = files.find((file) => file.id === id)!
      return {
        file_id: id,
        folder_id: file.folder_id,
        ancestor_ids: path(file.folder_id)
          .slice(0, -1)
          .map((f) => f.id),
        file_offset: 0,
        file_limit: 250,
      }
    }
  )
  vi.spyOn(foldersAPI, "moveFile").mockImplementation(async (id, target) => {
    const file = files.find((file) => file.id === id)!
    file.folder_id = target
    return { id, folder_id: target, moved: 1 }
  })
  vi.spyOn(foldersAPI, "moveFilesBatch").mockImplementation(
    async (ids, target) => {
      files.forEach((file) => {
        if (ids.includes(file.id)) file.folder_id = target
      })
      return { moved: ids.length, folder_id: target }
    }
  )
  vi.spyOn(foldersAPI, "move").mockImplementation(async (id, target) => {
    const folder = folders.find((folder) => folder.id === id)!
    folder.parent_id = target
    return { id, name: folder.name, parent_id: target, moved: 1 }
  })
}
function mount() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cases/case/evidence"]}>
        <div style={{ height: 740, width: "100%" }}>
          <Routes>
            <Route path="/cases/:id/evidence" element={<EvidenceExplorer />} />
          </Routes>
        </div>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
const dragEvent = (
  type: string,
  element: Element,
  dataTransfer: DataTransfer
) =>
  fireEvent(
    element,
    new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer })
  )
const nameCell = () => screen.getByRole("columnheader", { name: /Name/ })
const fileRow = (name: string) =>
  screen.getByRole("button", { name }).closest("tr")!
async function click(element: HTMLElement) {
  await act(async () => {
    await userEvent.click(element)
  })
}
async function chooseDestination(name: string) {
  const dialog = await screen.findByRole("dialog")
  await click(within(dialog).getByRole("button", { name }))
  await click(within(dialog).getByRole("button", { name: "Move here" }))
}

beforeEach(async () => {
  await act(async () => {
    await page.viewport(1560, 900)
  })
  vi.restoreAllMocks()
  mocks.upload.mockReset()
  mocks.canEdit = true
  useEvidenceStore.getState().resetForCase(crypto.randomUUID())
  useEvidenceStore.getState().resetForCase("case")
  useEvidenceStore.setState({
    sortBy: "name",
    sortDirection: "asc",
    nameWidth: null,
  })
  seed()
})
afterEach(() => {
  cleanup()
  client?.clear()
})

describe("Evidence usability in Chromium", () => {
  it("sorts headers, gives filenames available space, and resizes with pointer and keyboard", async () => {
    mount()
    await screen.findByRole("button", { name: longName })
    expect(nameCell()).toHaveAttribute("aria-sort", "ascending")
    expect(screen.queryByText("stale")).toBeNull()
    const autoWidth = nameCell().getBoundingClientRect().width
    expect(autoWidth).toBeGreaterThan(500)
    expect(
      screen.getByRole("button", { name: longName }).getBoundingClientRect()
        .width
    ).toBeGreaterThan(300)
    await act(async () => {
      await page
        .getByRole("button", { name: "Date added", exact: true })
        .click()
    })
    expect(
      screen.getByRole("columnheader", { name: "Date added" })
    ).toHaveAttribute("aria-sort", "descending")
    await waitFor(() =>
      expect(foldersAPI.getContents).toHaveBeenLastCalledWith(
        "case",
        null,
        expect.objectContaining({ sort_by: "date", sort_direction: "desc" }),
        expect.any(AbortSignal)
      )
    )
    const handle = screen.getByRole("separator", { name: "Resize Name column" })
    await act(async () => {
      fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientX: 400 })
      fireEvent.pointerMove(handle, { pointerId: 1, clientX: 520 })
      fireEvent.pointerUp(handle, { pointerId: 1 })
    })
    expect(useEvidenceStore.getState().nameWidth).toBeCloseTo(
      autoWidth + 120,
      0
    )
    await act(async () => {
      fireEvent.keyDown(handle, { key: "ArrowLeft" })
    })
    expect(useEvidenceStore.getState().nameWidth).toBeCloseTo(
      autoWidth + 100,
      0
    )
    expect(useEvidenceStore.getState().sortBy).toBe("date")
    await act(async () => {
      fireEvent.keyDown(handle, { key: "Enter" })
    })
    expect(useEvidenceStore.getState().nameWidth).toBeNull()
    await act(async () => {
      await page.screenshot({
        path: "../../../../../output/playwright/evidence-usability-wide.png",
      })
    })
    await act(async () => {
      await page.viewport(800, 900)
    })
    expect(
      screen.getByRole("table").parentElement!.scrollWidth
    ).toBeGreaterThan(screen.getByRole("table").parentElement!.clientWidth)
    await act(async () => {
      await page.screenshot({
        path: "../../../../../output/playwright/evidence-usability-narrow.png",
      })
    })
  })

  it("finds unopened nested files, changes scope and restores the browse folder", async () => {
    mount()
    await screen.findByRole("button", { name: longName })
    await act(async () => {
      await page
        .getByRole("textbox", { name: "Search files in case" })
        .fill("_100%")
    })
    await screen.findByRole("button", { name: "Report_100%.pdf" })
    expect(
      screen.getByText("Evidence root / Statements / September")
    ).toBeVisible()
    expect(foldersAPI.search).toHaveBeenLastCalledWith(
      "case",
      "_100%",
      "case",
      null,
      expect.any(Object),
      expect.any(AbortSignal)
    )
    await act(async () => {
      await page.screenshot({
        path: "../../../../../output/playwright/evidence-usability-search.png",
      })
    })
    await act(async () => {
      await page.getByRole("button", { name: "Archive", exact: true }).click()
    })
    expect(useEvidenceStore.getState()).toMatchObject({
      currentFolderId: "archive",
      fileSearchTerm: "",
    })
    await act(async () => {
      await page
        .getByRole("textbox", { name: "Search files in case" })
        .fill("_100%")
    })
    await screen.findByRole("button", { name: "Report_100%.pdf" })
    expect(screen.getByText("Upload destination: Archive")).toBeVisible()
    await act(async () => {
      await page.getByRole("combobox", { name: "Search scope" }).click()
    })
    await act(async () => {
      await page
        .getByRole("option", {
          name: "Files in this folder and subfolders",
          exact: true,
        })
        .click()
    })
    await screen.findByText("No matching filenames")
    await act(async () => {
      await page.getByRole("button", { name: "Clear search" }).click()
    })
    expect(useEvidenceStore.getState().currentFolderId).toBe("archive")
  })

  it.each([
    ["name", "asc"],
    ["name", "desc"],
    ["date", "asc"],
    ["date", "desc"],
  ] as const)(
    "reveals search results using %s %s",
    async (sortBy, sortDirection) => {
      useEvidenceStore.setState({ sortBy, sortDirection })
      mount()
      await screen.findByRole("button", { name: longName })
      await act(async () => {
        await page
          .getByRole("textbox", { name: "Search files in case" })
          .fill("_100%")
      })
      await screen.findByRole("link", { name: "Open file location" })
      await act(async () => {
        await page.getByRole("link", { name: "Open file location" }).click()
      })
      await waitFor(() => expect(fileRow("Report_100%.pdf")).toHaveFocus())
      expect(useEvidenceStore.getState()).toMatchObject({
        currentFolderId: "child",
        fileSearchTerm: "",
        sortBy,
        sortDirection,
      })
      expect(foldersAPI.getFileLocation).toHaveBeenCalledWith(
        "case",
        "nested",
        expect.any(AbortSignal),
        { sort_by: sortBy, sort_direction: sortDirection }
      )
    }
  )

  it("cancels superseded filename requests and renders errors separately from empty results", async () => {
    let signal: AbortSignal | undefined
    vi.mocked(foldersAPI.search).mockImplementation(
      (_case, _query, _scope, _folder, _params, nextSignal) => {
        signal = nextSignal
        return new Promise((_resolve, reject) =>
          nextSignal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError"))
          )
        )
      }
    )
    mount()
    await screen.findByRole("button", { name: longName })
    await act(async () => {
      await page
        .getByRole("textbox", { name: "Search files in case" })
        .fill("first")
    })
    await waitFor(() => expect(signal).toBeDefined())
    const firstSignal = signal!
    vi.mocked(foldersAPI.search).mockRejectedValue(
      new Error("Search service unavailable")
    )
    await act(async () => {
      await page
        .getByRole("textbox", { name: "Search files in case" })
        .fill("second")
    })
    await waitFor(() => expect(firstSignal.aborted).toBe(true))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Search service unavailable"
    )
    expect(screen.queryByText("No matching filenames")).toBeNull()
  })

  it("keeps selection after a failed move and then completes the menu move", async () => {
    vi.mocked(foldersAPI.moveFile).mockRejectedValueOnce(
      new Error("Destination was removed; choose another folder")
    )
    mount()
    await screen.findByRole("button", { name: longName })
    await click(screen.getByRole("checkbox", { name: `Select ${longName}` }))
    await click(
      within(fileRow(longName)).getByRole("button", {
        name: `Actions for ${longName}`,
      })
    )
    await act(async () => {
      await page
        .getByRole("menuitem", { name: "Move to…", exact: true })
        .click()
    })
    const dialog = await screen.findByRole("dialog")
    expect(
      within(dialog).getByRole("button", { name: /Evidence root/ })
    ).toBeDisabled()
    await chooseDestination("Archive")
    await screen.findByRole("alert")
    expect(useEvidenceStore.getState().selectedFileIds.has("a")).toBe(true)
    await act(async () => {
      await page.screenshot({
        path: "../../../../../output/playwright/evidence-usability-move.png",
      })
    })
    await click(within(dialog).getByRole("button", { name: "Move here" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    expect(useEvidenceStore.getState().selectedFileIds.size).toBe(0)
    expect(files.find((f) => f.id === "a")?.folder_id).toBe("archive")
  })

  it("moves a selected batch through the picker and a folder through its tree menu", async () => {
    mount()
    await screen.findByRole("button", { name: longName })
    await click(
      screen.getByRole("checkbox", { name: "Select all files on this page" })
    )
    await act(async () => {
      await page.getByRole("button", { name: "Move to…", exact: true }).click()
    })
    await chooseDestination("Archive")
    await waitFor(() =>
      expect(foldersAPI.moveFilesBatch).toHaveBeenCalledWith(
        ["a", "b"],
        "archive"
      )
    )
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    const statements = screen.getAllByRole("button", { name: "Statements" })[0]
    await act(async () => {
      await userEvent.click(statements, { button: "right" })
    })
    await act(async () => {
      await page
        .getByRole("menuitem", { name: "Move to…", exact: true })
        .click()
    })
    const dialog = await screen.findByRole("dialog")
    expect(
      within(dialog).getByRole("button", { name: /September/ })
    ).toBeDisabled()
    await chooseDestination("Archive")
    await waitFor(() =>
      expect(foldersAPI.move).toHaveBeenCalledWith("parent", "archive")
    )
  })

  it("drags selected files to folder rows, and an unselected file to the root breadcrumb", async () => {
    mount()
    await screen.findByRole("button", { name: longName })
    await click(
      screen.getByRole("checkbox", { name: "Select all files on this page" })
    )
    const destination = within(screen.getByRole("table")).getByRole("button", {
      name: "Archive",
    })
    await act(async () => {
      await userEvent.dragAndDrop(
        screen.getByRole("button", { name: longName }),
        destination
      )
    })
    await waitFor(() =>
      expect(foldersAPI.moveFilesBatch).toHaveBeenCalledWith(
        ["a", "b"],
        "archive"
      )
    )
    expect(screen.queryByText("Drop files to upload")).toBeNull()
    await click(screen.getAllByRole("button", { name: "Archive" })[0])
    await screen.findByRole("button", { name: longName })
    await click(screen.getByRole("checkbox", { name: `Select ${longName}` }))
    await act(async () => {
      await userEvent.dragAndDrop(
        screen.getByRole("button", { name: "Zulu.pdf" }),
        within(
          screen.getByRole("navigation", { name: "Evidence folder path" })
        ).getByRole("button", { name: "Evidence root" })
      )
    })
    await waitFor(() =>
      expect(foldersAPI.moveFile).toHaveBeenCalledWith("b", null)
    )
    expect(useEvidenceStore.getState().selectedFileIds.has("a")).toBe(true)
  })

  it("expands valid tree drag targets and keeps operating-system uploads in the browse folder", async () => {
    mount()
    await screen.findByRole("button", { name: longName })
    await waitFor(() =>
      expect(fileRow(longName)).toHaveAttribute("draggable", "true")
    )
    const transfer = new DataTransfer()
    await act(async () => {
      dragEvent("dragstart", fileRow(longName), transfer)
    })
    expect(transfer.types).toContain(EVIDENCE_DRAG_TYPE)
    const target = screen.getAllByRole("button", { name: "Statements" })[0]
    await act(async () => {
      dragEvent("dragover", target, transfer)
    })
    expect(target).toHaveAttribute("data-drop-active", "true")
    await waitFor(() =>
      expect(useEvidenceStore.getState().expandedFolderIds.has("parent")).toBe(
        true
      )
    )
    await act(async () => {
      dragEvent("dragend", fileRow(longName), transfer)
    })
    await click(screen.getAllByRole("button", { name: "Archive" })[0])
    await act(async () => {
      await page
        .getByRole("textbox", { name: "Search files in case" })
        .fill("_100%")
    })
    await screen.findByRole("button", { name: "Report_100%.pdf" })
    mocks.upload.mockImplementation(
      (_data: unknown, options: { onSuccess: () => void }) =>
        options.onSuccess()
    )
    const upload = new DataTransfer()
    upload.items.add(
      new File(["evidence"], "upload.txt", { type: "text/plain" })
    )
    await act(async () => {
      dragEvent("dragenter", screen.getByRole("table"), upload)
    })
    const overlay = await screen.findByText("Drop files to upload")
    await act(async () => {
      dragEvent("drop", overlay, upload)
    })
    expect(mocks.upload).toHaveBeenCalledWith(
      expect.objectContaining({
        folderId: "archive",
        files: [expect.any(File)],
      }),
      expect.any(Object)
    )
    await waitFor(() =>
      expect(screen.queryByText("Drop files to upload")).toBeNull()
    )
    await act(async () => {
      dragEvent("dragenter", screen.getByRole("table"), upload)
    })
    await waitFor(() => expect(screen.getByText("Drop files to upload")).toBeVisible())
    await act(async () => {
      dragEvent("dragleave", screen.getByRole("table"), upload)
    })
    await waitFor(() =>
      expect(screen.queryByText("Drop files to upload")).toBeNull()
    )
  })
  it("moves the currently open folder by dragging and refreshes its ancestry", async () => {
    mount()
    await screen.findByRole("button", { name: longName })
    await click(screen.getAllByRole("button", { name: "Statements" })[0])
    const trail = screen.getByRole("navigation", {
      name: "Evidence folder path",
    })
    await waitFor(() =>
      expect(
        within(trail).getByRole("button", { name: "Statements" })
      ).toBeVisible()
    )
    const source = screen.getAllByRole("button", { name: "Statements" })[0]
    const target = screen.getByRole("button", { name: "Archive" })
    await act(async () => {
      await userEvent.dragAndDrop(source, target)
    })
    await waitFor(() =>
      expect(foldersAPI.move).toHaveBeenCalledWith("parent", "archive")
    )
    expect(useEvidenceStore.getState().currentFolderId).toBe("parent")
    await waitFor(() =>
      expect(
        within(trail).getByRole("button", { name: "Archive" })
      ).toBeVisible()
    )
    await waitFor(() =>
      expect(useEvidenceStore.getState().expandedFolderIds.has("archive")).toBe(
        true
      )
    )
    // The same folder can return to root from its row menu in the destination.
    await click(screen.getAllByRole("button", { name: "Archive" })[0])
    await waitFor(() =>
      expect(
        within(screen.getByRole("table")).getByRole("button", {
          name: "Statements",
        })
      ).toBeVisible()
    )
    await click(
      within(screen.getByRole("table")).getByRole("button", {
        name: "Actions for Statements",
      })
    )
    await act(async () => {
      await page
        .getByRole("menuitem", { name: "Move to…", exact: true })
        .click()
    })
    await chooseDestination("Evidence root")
    await waitFor(() =>
      expect(foldersAPI.move).toHaveBeenLastCalledWith("parent", null)
    )
  })

  it("disables movement for read-only case members", async () => {
    mocks.canEdit = false
    mount()
    await screen.findByRole("button", { name: longName })
    expect(fileRow(longName)).toHaveAttribute("draggable", "false")
    await click(
      within(fileRow(longName)).getByRole("button", {
        name: `Actions for ${longName}`,
      })
    )
    expect(
      await screen.findByRole("menuitem", { name: "Move to…" })
    ).toHaveAttribute("aria-disabled", "true")
    expect(foldersAPI.moveFile).not.toHaveBeenCalled()
  })

  it("resolves the page again when sorting changes during a location request", async () => {
    let complete: (
      value: Awaited<ReturnType<typeof foldersAPI.getFileLocation>>
    ) => void = () => {}
    vi.mocked(foldersAPI.getFileLocation).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        })
    )
    mount()
    await screen.findByRole("button", { name: longName })
    await act(async () => {
      await page
        .getByRole("textbox", { name: "Search files in case" })
        .fill("_100%")
    })
    await screen.findByRole("link", { name: "Open file location" })
    await act(async () => {
      await page.getByRole("link", { name: "Open file location" }).click()
    })
    await act(async () => {
      await page.getByRole("button", { name: "Name", exact: true }).click()
    })
    await act(async () => {
      complete({
        file_id: "nested",
        folder_id: "child",
        ancestor_ids: ["parent"],
        file_offset: 250,
        file_limit: 250,
      })
    })
    await waitFor(() =>
      expect(useEvidenceStore.getState().currentFolderId).toBe("child")
    )
    expect(foldersAPI.getFileLocation).toHaveBeenLastCalledWith(
      "case",
      "nested",
      expect.any(AbortSignal),
      { sort_by: "name", sort_direction: "desc" }
    )
    expect(useEvidenceStore.getState().filePage).toBe(0)
  })
})
