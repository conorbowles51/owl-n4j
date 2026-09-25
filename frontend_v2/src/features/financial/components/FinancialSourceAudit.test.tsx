import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { FinancialSourceAudit } from "./FinancialSourceAudit"
import {
  auditDetail,
  auditGroup,
  auditList,
} from "../test/source-audit-fixtures"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { StatementFilesPanel } from "./StatementFilesPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("./StatementRecoveryPanel", () => ({
  StatementRecoveryPanel: () => null,
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: (props: {
    evidenceId: string
    documentName: string
    onOpenChange: (open: boolean) => void
  }) => (
    <div role="dialog" aria-label="Original source">
      {props.documentName}
      <output>{props.evidenceId}</output>
      <button onClick={() => props.onOpenChange(false)}>Close original</button>
    </div>
  ),
}))

function mount(children: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}
const groups = Array.from({ length: 52 }, (_, index) => auditGroup(index))
function respond(url: string) {
  const parsed = new URL(url, "http://localhost")
  if (parsed.pathname === "/api/financial/source-audit")
    return auditList(
      groups,
      parsed.searchParams.get("visibility") || "visible",
      Number(parsed.searchParams.get("offset"))
    )
  if (parsed.pathname.startsWith("/api/financial/source-audit/")) {
    const id = parsed.pathname.split("/").at(-1)!
    const group = groups.find(
      (group) => group.current_file_id === id || group.root_file_id === id
    )!
    return auditDetail(
      group,
      id,
      Number(parsed.searchParams.get("text_offset"))
    )
  }
  throw Error(`Unexpected request ${url}`)
}
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url) => respond(url))
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
})

it("does not query while collapsed and reads only paginated metadata until a source is inspected", async () => {
  mount(<FinancialSourceAudit caseId="case" onFindFile={vi.fn()} />)
  expect(fetchAPI).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Review Financial sources" })
  )
  expect(
    await screen.findByRole("heading", { name: "Sources 1–50 of 51" })
  ).toBeVisible()
  expect(
    screen.getByRole("list", { name: "Financial sources for inspection" })
      .children
  ).toHaveLength(50)
  expect(fetchAPI).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "Next sources" }))
  expect(
    await screen.findByRole("heading", { name: "Sources 51–51 of 51" })
  ).toHaveFocus()
  fireEvent.change(screen.getByLabelText("Sources to review"), {
    target: { value: "hidden" },
  })
  expect(
    await screen.findByRole("heading", { name: "Sources 1–1 of 1" })
  ).toBeVisible()
  expect(
    screen.getByRole("button", { name: "Previous sources" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Inspect source" }))
  expect(
    await screen.findByText(/No stored text is available/)
  ).toHaveTextContent("financial relevance is unknown")
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(
        ([, options]) => !options?.method || options.method === "GET"
      )
  ).toBe(true)
})

it("keeps source identity through excerpt pages, alternate readings and original viewing", async () => {
  mount(<FinancialSourceAudit caseId="case" onFindFile={vi.fn()} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Review Financial sources" })
  )
  fireEvent.click(
    (await screen.findAllByRole("button", { name: "Inspect source" }))[0]
  )
  expect(await screen.findByText(/Synthetic retained text/)).toHaveTextContent(
    "<script>"
  )
  expect(document.querySelector("script")).toBeNull()
  expect(screen.getByText(/characters 1–4000 of 6000/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next text" }))
  expect(await screen.findByText(/Later retained text/)).toBeVisible()
  expect(screen.getByText(/characters 4001–6000 of 6000/)).toBeVisible()
  fireEvent.change(screen.getByLabelText("Source reading"), {
    target: { value: "source-0" },
  })
  expect(await screen.findByText(/No stored text is available/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Open original" }))
  expect(
    screen.getByRole("dialog", { name: "Original source" })
  ).toHaveTextContent("source-0")
  fireEvent.click(screen.getByRole("button", { name: "Close original" }))
  expect(screen.getByLabelText("Source reading")).toHaveValue("source-0")
  expect(
    screen.getByRole("link", { name: "Open in Evidence" })
  ).toHaveAttribute("href", "/cases/case/evidence?file=source-0&from=financial")
  fireEvent.click(screen.getAllByRole("button", { name: "Inspect source" })[0])
  expect(
    await screen.findByText(
      "Saved financial records or their history are retained."
    )
  ).toBeVisible()
  expect(screen.getAllByRole("button", { name: "Close details" })).toHaveLength(
    1
  )
})

it("rejects cross-case metadata and permits a read-only retry without displaying the wrong files", async () => {
  vi.mocked(fetchAPI).mockResolvedValueOnce(
    auditList(groups, "visible", 0, "other-case")
  )
  mount(<FinancialSourceAudit caseId="case" onFindFile={vi.fn()} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Review Financial sources" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Source review could not be loaded for this case"
  )
  expect(
    screen.queryByRole("heading", { name: "Shared name.txt" })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Refresh source review" }))
  expect(
    await screen.findByRole("heading", { name: "Sources 1–50 of 51" })
  ).toBeVisible()
})

it("reports detail and locate errors and preserves the inventory for retry", async () => {
  const find = vi
    .fn()
    .mockRejectedValue(Error("The source moved. Refresh its file list."))
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("source-audit/reading"))
      throw new ApiError("Stored reading is not available in this case.", 404)
    return respond(url)
  })
  mount(<FinancialSourceAudit caseId="case" onFindFile={find} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Review Financial sources" })
  )
  fireEvent.click(
    (await screen.findAllByRole("button", { name: "Inspect source" }))[0]
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Stored reading is not available"
  )
  fireEvent.click(screen.getAllByRole("button", { name: "Find in files" })[0])
  await waitFor(() => expect(find).toHaveBeenCalledWith("reading-0"))
  expect(
    await screen.findByText("The source moved. Refresh its file list.")
  ).toBeVisible()
  expect(
    screen.getByRole("heading", { name: "Sources 1–50 of 51" })
  ).toBeVisible()
})

it("finds the exact file family despite duplicate names, focuses its controls and returns to the retained audit", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("/source-audit")) return respond(url)
    if (url.startsWith("/api/evidence?"))
      return {
        files: groups.slice(0, 3).map((group) => ({
          id: group.current_file_id,
          case_id: "case",
          original_filename: group.filename,
          status: "processed",
          statement_root_evidence_id: group.root_file_id,
          financial_removed: group.visibility === "hidden",
        })),
      }
    if (url.startsWith("/api/evidence-upload-")) return []
    if (url.includes("/statement-import/files?"))
      return { case_id: "case", files: [], truncated: false }
    throw Error(`Unexpected request ${url}`)
  })
  mount(<StatementFilesPanel caseId="case" register />)
  fireEvent.click(
    screen.getByRole("button", { name: "Review Financial sources" })
  )
  fireEvent.click(
    (await screen.findAllByRole("button", { name: "Find in files" }))[1]
  )
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "1 matching files" })
    ).toHaveFocus()
  )
  const source = screen.getByRole("article", {
    name: "Financial source Shared name.txt",
  })
  expect(
    within(source).getByRole("link", { name: "Open source in Evidence" })
  ).toHaveAttribute(
    "href",
    "/cases/case/evidence?file=reading-1&from=financial"
  )
  fireEvent.click(screen.getByRole("button", { name: "Back to source review" }))
  expect(
    screen.getByRole("region", { name: "Review Financial sources" })
      .parentElement
  ).toHaveFocus()
  expect(
    screen.getByRole("heading", { name: "Sources 1–50 of 51" })
  ).toBeVisible()
  expect(
    screen.getByRole("heading", { name: "2 matching files" })
  ).toBeVisible()
})
