import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { EvidenceExplorer } from "./EvidenceExplorer"
import "@/styles/globals.css"

vi.mock("../hooks/use-folder-mutations", () => ({ useCreateFolder: () => ({ mutate: vi.fn() }), useDeleteFolder: () => ({ mutate: vi.fn() }) }))
vi.mock("../hooks/use-evidence-detail", () => ({ useDeleteEvidence: () => ({ mutate: vi.fn() }), useProcessBackground: () => ({ mutate: vi.fn() }) }))
vi.mock("@/features/cases/hooks/use-deleted-items", () => ({ useDeletedItemsEnabled: () => false }))
vi.mock("./FolderTreeSidebar", () => ({
  FolderTreeSidebar: ({ onCollapse }: { onCollapse?: () => void }) => (
    <nav aria-label="Folder tree" style={{ height: "100%" }}><button onClick={onCollapse}>Collapse sidebar</button></nav>
  ),
}))
vi.mock("./FileListPanel", () => ({ FileListPanel: () => <section aria-label="Files" style={{ height: "100%" }} /> }))
vi.mock("./CreateFolderDialog", () => ({ CreateFolderDialog: () => null }))
vi.mock("./DeleteFolderDialog", () => ({ DeleteFolderDialog: () => null }))
vi.mock("./DeleteEvidenceDialog", () => ({ DeleteEvidenceDialog: () => null }))
vi.mock("./DeletedEvidenceDialog", () => ({ DeletedEvidenceDialog: () => null }))
vi.mock("./FolderContextDialog", () => ({ FolderContextDialog: () => null }))
vi.mock("./CaseProcessingProfileDialog", () => ({ CaseProcessingProfileDialog: () => null }))

function mount() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case-1/evidence"]}>
        <div style={{ height: "100dvh", width: "100%" }}>
          <Routes><Route path="/cases/:id/evidence" element={<EvidenceExplorer />} /></Routes>
        </div>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("Evidence folders at phone width (followups m11172304218882)", () => {
  afterEach(cleanup)

  it("puts the folders above the files at full width on a 390 px screen, beside them on a wide one", async () => {
    await page.viewport(390, 844)
    mount()
    const folders = (await screen.findByRole("navigation", { name: "Folder tree" })).getBoundingClientRect()
    const files = screen.getByRole("region", { name: "Files" }).getBoundingClientRect()
    // the old layout gave the folders a fifth of the width: 78 px, under the 116 px their header needs
    expect(folders.width).toBeGreaterThan(300)
    expect(files.top).toBeGreaterThanOrEqual(folders.bottom - 1)
    cleanup()
    await page.viewport(1500, 900)
    mount()
    const wide = (await screen.findByRole("navigation", { name: "Folder tree" })).getBoundingClientRect()
    const wideFiles = screen.getByRole("region", { name: "Files" }).getBoundingClientRect()
    expect(wide.width).toBeLessThan(600)
    expect(wideFiles.left).toBeGreaterThanOrEqual(wide.right - 1)
  })

  it("folds the folders away with Collapse sidebar", async () => {
    await page.viewport(1500, 900)
    mount()
    const nav = await screen.findByRole("navigation", { name: "Folder tree" })
    expect(nav.getBoundingClientRect().width).toBeGreaterThan(100)
    screen.getByRole("button", { name: "Collapse sidebar" }).click()
    await expect.poll(() => screen.queryByRole("navigation", { name: "Folder tree" })?.getBoundingClientRect().width ?? 0).toBeLessThan(5)
  })
})
