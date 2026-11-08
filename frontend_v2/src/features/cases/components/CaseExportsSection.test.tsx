import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { CaseExport, CaseExportList } from "../exports-api"
import { CaseExportsSection } from "./CaseExportsSection"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const complete: CaseExport = {
  id: "e1",
  status: "complete",
  phase: null,
  done: 10,
  total: 10,
  error: null,
  whole: false,
  requested_by: "Neil Byrne",
  created_at: "2026-11-08T10:00:00Z",
  finished_at: "2026-11-08T10:05:00Z",
  expires_at: "2026-11-15T10:05:00Z",
  size_bytes: 120 * 1024 * 1024,
  sha256: "c".repeat(64),
  rows: 51234,
  tables: 177,
  evidence_files: 42,
  graph: { nodes: 900, relationships: 1200 },
  vectors: { chunks: 10, entities: 3 },
  missing_from_disk: 0,
  differ_from_recorded_hash: 0,
  rows_private_to_others_left_out: { chat_conversations: 2 },
}

const listAnswer = (exports: CaseExport[]): CaseExportList => ({
  exports,
  holds: "A complete copy of the case: evidence files, financial and phone records.",
  private_note: "Chats belong to the person who had them.",
  left_out: "Left out: who can open the case.",
  kept: "A package is kept for 7 days, then removed.",
  carries_all_private: false,
})

const renderSection = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CaseExportsSection caseId="case-1" />
    </QueryClientProvider>
  )

beforeEach(() => vi.mocked(fetchAPI).mockReset())

it("states what a package holds before one is asked for, in the server's words", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(listAnswer([]))
  renderSection()
  expect((await screen.findByTestId("case-export-holds")).textContent).toContain("A complete copy of the case")
  expect(screen.getByText(/Chats belong to the person/)).toBeTruthy()
  expect(screen.getByText(/kept for 7 days/)).toBeTruthy()
  expect(String(vi.mocked(fetchAPI).mock.calls[0][0])).toBe("/api/cases/case-1/exports")
})

it("asks the server to build the package", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(listAnswer([]))
  renderSection()
  await screen.findByTestId("case-export-holds")
  fireEvent.click(await screen.findByRole("button", { name: /Build the package/ }))
  await waitFor(() =>
    expect(
      vi
        .mocked(fetchAPI)
        .mock.calls.some(
          ([url, options]) =>
            String(url) === "/api/cases/case-1/exports" &&
            (options as { method?: string } | undefined)?.method === "POST"
        )
    ).toBe(true)
  )
})

it("shows a running export's progress and offers only Cancel", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(
    listAnswer([{ ...complete, status: "running", phase: "Records: payments", done: 3, total: 10, sha256: null }])
  )
  renderSection()
  expect((await screen.findByTestId("case-export-progress")).textContent).toContain("Records: payments (3 of 10 steps)")
  expect(screen.getByRole("button", { name: /Cancel/ })).toBeTruthy()
  expect(screen.queryByText(/Download/)).toBeNull()
  expect(screen.getByRole("button", { name: /An export is running/ })).toHaveProperty("disabled", true)
})

it("offers a finished package as a streamed link with its counts, hash and keep time", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(listAnswer([complete]))
  renderSection()
  const link = (await screen.findByRole("link", { name: /Download/ })) as HTMLAnchorElement
  expect(link.getAttribute("href")).toBe("/api/cases/case-1/exports/e1/download")
  const contents = screen.getByTestId("case-export-contents").textContent ?? ""
  expect(contents).toContain("177 tables")
  expect(contents).toContain("42 evidence files")
  expect(screen.getByText(/2 chat conversations/)).toBeTruthy()
  expect(screen.getByText(new RegExp(`SHA-256 ${"c".repeat(16)}`))).toBeTruthy()
})

it("says why an export failed", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(
    listAnswer([{ ...complete, status: "failed", error: "Processing is running in this case: 3 documents." }])
  )
  renderSection()
  expect(await screen.findByText(/Processing is running in this case/)).toBeTruthy()
})
