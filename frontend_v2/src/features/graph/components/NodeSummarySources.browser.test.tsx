import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { useGraphStore } from "@/stores/graph.store"
import { evidenceAPI } from "@/features/evidence/api"
import type { NodeDetail } from "@/types/graph.types"
import { NodeDetailSheet } from "./NodeDetailSheet"
import "@/styles/globals.css"

const mocks = vi.hoisted(() => ({ detail: null as NodeDetail | null }))
vi.mock("../hooks/use-node-details", () => ({
  useNodeDetails: () => ({ data: mocks.detail, isLoading: false }),
}))
vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: {} }),
}))
vi.mock("@/features/cases/hooks/use-case-permissions", () => ({
  useCasePermissions: () => ({ canEdit: false }),
}))
vi.mock("@/features/significant/hooks/use-significant", () => ({
  useSignificantManifest: () => ({ entityKeySet: new Set() }),
  useAddSignificantEntities: () => ({ mutateAsync: vi.fn() }),
  useRemoveSignificantEntities: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock("@/features/significant/components/SignificantEntityButton", () => ({
  SignificantEntityButton: () => null,
}))
vi.mock("@/features/dossiers", () => ({
  useCreateDossier: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock("@/features/notebook/components/NotebookLinkedNotes", () => ({
  NotebookLinkedNotes: () => null,
}))
vi.mock("./ConnectionsList", () => ({
  ConnectionsList: () => <p>No connections</p>,
}))
vi.mock("./MultiNodePanel", () => ({ MultiNodePanel: () => null }))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({
    objectUrl: "about:blank",
    loading: false,
    error: null,
  }),
  openProtectedFile: vi.fn(),
}))

const filename = `2026_Consolidated_Bank_Statement_${"Transaction_Appendix_".repeat(6)}Final.pdf`
const fixture: NodeDetail = {
  key: "entity-1",
  label: "Harbor Trading",
  type: "company",
  summary: `## Financial activity
The account received three transfers [${filename}](doc://${filename}/4).
Later transactions used the same account [${filename}](doc://${filename}/9).
A withdrawal followed [Withdrawal record](evidence://withdrawals.pdf).

## Source References
- [${filename}](evidence://${filename})
- [withdrawals.pdf](evidence://withdrawals.pdf)`,
  properties: { source_files: [filename, "metadata-only.pdf"] },
  sources: [{ fileId: "old-1", fileName: "metadata-only.pdf" }],
  connections: [],
  verified_facts: [
    {
      text: "A separately verified fact",
      source_doc: "fact-source.pdf",
      page: 2,
    },
  ],
}

function Panel({ client, width }: { client: QueryClient; width: number }) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <div style={{ width, height: 940, maxWidth: "100vw" }}>
          <NodeDetailSheet caseId="case-1" />
        </div>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("entity summary sources in Chromium", () => {
  beforeEach(async () => {
    await page.viewport(1280, 1000)
    vi.restoreAllMocks()
    mocks.detail = fixture
    useGraphStore.getState().selectNodes(["entity-1"])
    vi.spyOn(evidenceAPI, "findByFilename").mockResolvedValue({
      found: true,
      evidence_id: "evidence-1",
    })
  })
  afterEach(cleanup)

  for (const width of [390, 480]) {
    it(`replaces metadata sources with matching citations and wrapped filenames at ${width}px`, async () => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      })
      render(<Panel client={client} width={width} />)
      const list = screen.getByRole("region", { name: "Summary sources" })
      expect(within(list).getAllByRole("listitem")).toHaveLength(2)
      expect(
        screen.queryByRole("heading", { name: "Sources" })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole("heading", { name: "Source References" })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole("button", { name: "metadata-only.pdf" })
      ).not.toBeInTheDocument()
      expect(
        within(list).queryByText("metadata-only.pdf")
      ).not.toBeInTheDocument()
      expect(screen.getByText("[S1, p.4]")).toBeVisible()
      expect(screen.getByText("[S1, p.9]")).toBeVisible()
      expect(screen.getByText("[S2]")).toBeVisible()
      expect(screen.getAllByText(filename, { exact: true })).toHaveLength(1)
      const fullName = within(list).getByRole("button", {
        name: `Open source S1: ${filename}`,
      })
      expect(fullName.scrollWidth).toBeLessThanOrEqual(fullName.clientWidth + 1)
      expect(fullName.getBoundingClientRect().right).toBeLessThanOrEqual(width)
      expect(fullName.getBoundingClientRect().height).toBeGreaterThan(30)
      expect(
        screen.getByRole("button", { name: "Source: fact-source.pdf p.2" })
      ).toBeVisible()
      if (width === 390)
        await page.screenshot({
          path: "../../../../../output/playwright/entity-summary-sources.png",
        })

      await act(async () => {
        await page
          .getByRole("button", {
            name: `Open source S1: ${filename}, p.9`,
            exact: true,
          })
          .click()
      })
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: filename })).toBeVisible()
      )
      expect(document.querySelector("iframe")?.getAttribute("src")).toContain(
        "#page=9"
      )
      expect(
        screen.getByRole("link", { name: "Open file location" })
      ).toBeVisible()
      fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      )
      fireEvent.click(
        within(list).getByRole("button", { name: "Open source S1, page 4" })
      )
      await waitFor(() =>
        expect(document.querySelector("iframe")?.getAttribute("src")).toContain(
          "#page=4"
        )
      )
      expect(evidenceAPI.findByFilename).toHaveBeenLastCalledWith(
        filename,
        "case-1"
      )
      cleanup()
      client.clear()
    })
  }

  it("updates numbering with the selected summary and hides the list when there are no links", () => {
    const client = new QueryClient()
    const view = render(<Panel client={client} width={390} />)
    mocks.detail = {
      ...fixture,
      key: "entity-2",
      summary: "A new finding [report](doc://new.pdf/3).",
    }
    view.rerender(<Panel client={client} width={390} />)
    expect(screen.getByText("[S1, p.3]")).toBeVisible()
    expect(screen.queryByText("[S2]")).not.toBeInTheDocument()
    expect(
      within(
        screen.getByRole("region", { name: "Summary sources" })
      ).getAllByRole("listitem")
    ).toHaveLength(1)
    mocks.detail = {
      ...fixture,
      summary: "An older plain-text summary mentioning file.pdf.",
    }
    view.rerender(<Panel client={client} width={390} />)
    expect(
      screen.queryByRole("region", { name: "Summary sources" })
    ).not.toBeInTheDocument()
    expect(
      screen.getByText("An older plain-text summary mentioning file.pdf.")
    ).toBeVisible()
    cleanup()
    client.clear()
  })
})
