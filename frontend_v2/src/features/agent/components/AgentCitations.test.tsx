import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { AgentCitationProvider, AgentMarkdown, NO_CITATION_PAGE } from "./AgentCitations"

const FILE = "0b6c2a1e-7d4f-4c1a-9e2b-5f3a8c9d0e11"
const OTHER = "1c7d3b2f-8e5a-4d2b-8f3c-6a4b9d0e1f22"
const TXN = "2d8e4c3a-9f6b-4e3c-9a4d-7b5c0e1f2a33"
const GONE = "3e9f5d4b-0a7c-4f4d-8b5e-8c6d1f2a3b44"
const CASE = "4f0a6e5c-1b8d-4a5e-9c6f-9d7e2a3b4c55"

const resolutions = vi.hoisted(() => ({ items: [] as Record<string, unknown>[], calls: [] as string[][] }))
vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<object>()),
  fetchAPI: vi.fn(async (url: string, opts: { body: { hrefs: string[] } }) => {
    if (url !== "/api/citations/resolve") throw new Error(`unexpected ${url}`)
    resolutions.calls.push(opts.body.hrefs)
    return { items: resolutions.items.filter((item) => opts.body.hrefs.includes(item.href as string)) }
  }),
}))
vi.mock("@/lib/protected-file", () => ({
  openProtectedFile: vi.fn(),
  useProtectedObjectUrl: () => ({ objectUrl: "blob:source", loading: false, error: null }),
}))
vi.mock("@/features/phones/components/RecordPanel", () => ({
  PhoneRecordPanel: ({ recordUid, onClose }: { recordUid: string; onClose: () => void }) => (
    <section aria-label="Record behind this message">
      <p>Record {recordUid}</p>
      <button type="button" onClick={onClose}>Close record</button>
    </section>
  ),
}))
vi.mock("@/components/ui/evidence-pdf-document", () => ({
  EvidencePdfDocument: ({ page }: { page: number }) => <p>Showing source page {page}</p>,
}))

function answer(content: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AgentCitationProvider caseId={CASE}>
          <AgentMarkdown content={content} />
        </AgentCitationProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const ok = (href: string, extra: Record<string, unknown>) => ({ href, status: "ok", page_given: false, legacy: false, ...extra })

beforeEach(() => {
  resolutions.items = []
  resolutions.calls = []
})

it("opens a doc:// citation by file id at its cited page", async () => {
  resolutions.items = [ok(`doc://${FILE}/4`, { scheme: "doc", evidence_file_id: FILE, filename: "March statement.pdf", page: 4, page_given: true })]
  answer(`The deposit is on [March statement.pdf, p.4](doc://${FILE}/4).`)
  fireEvent.click(await screen.findByRole("button", { name: "March statement.pdf, p.4" }))
  expect(await screen.findByRole("heading", { name: "March statement.pdf" })).toBeVisible()
  expect(await screen.findByText("Showing source page 4")).toBeVisible()
  expect(screen.queryByText(NO_CITATION_PAGE)).toBeNull()
  // one request checks every citation of the answer
  expect(resolutions.calls[0]).toEqual([`doc://${FILE}/4`])
})

it("opens a citation with no page at the start of the file and says the page was not given", async () => {
  resolutions.items = [ok(`doc://${FILE}`, { scheme: "doc", evidence_file_id: FILE, filename: "March statement.pdf" })]
  answer(`See [March statement.pdf](doc://${FILE}).`)
  fireEvent.click(await screen.findByRole("button", { name: "March statement.pdf" }))
  expect(await screen.findByText(NO_CITATION_PAGE)).toBeVisible()
  expect(NO_CITATION_PAGE).toMatch(/^Page not given/)
})

it("offers the files that share an old citation's filename and never picks one", async () => {
  const href = "doc://Statement.pdf/2"
  resolutions.items = [{
    href, scheme: "doc", status: "ambiguous", page: 2, page_given: true, legacy: true, filename: "Statement.pdf",
    reason: "2 files in this case are called Statement.pdf; the citation does not say which. Choose one.",
    candidates: [
      { evidence_file_id: FILE, filename: "Statement.pdf", uploaded_at: "2026-10-01T10:00:00Z", size: 1000 },
      { evidence_file_id: OTHER, filename: "Statement.pdf", uploaded_at: "2026-10-02T10:00:00Z", size: 2000 },
    ],
  }]
  answer(`On [Statement.pdf, p.2](${href}).`)
  const link = await screen.findByRole("button", { name: /Statement\.pdf, p\.2/ })
  expect(await within(link).findByText("(choose file)")).toBeVisible()
  fireEvent.click(link)
  const list = await screen.findByRole("list", { name: "Files with this name" })
  expect(within(list).getAllByRole("button")).toHaveLength(2)
  expect(screen.queryByText("Showing source page 2")).toBeNull()
  fireEvent.click(within(list).getAllByRole("button")[1])
  expect(await screen.findByText("Showing source page 2")).toBeVisible()
})

it("links a txn:// row and an old payment link to the Financial page on that payment", async () => {
  const old = `/cases/${CASE}/financial?view=transactions&payment=${TXN}`
  resolutions.items = [ok(`txn://${TXN}`, { scheme: "txn", transaction_id: TXN, page: 3, page_given: true }),
    ok(old, { scheme: "txn", transaction_id: TXN, legacy: true })]
  answer(`Paid [12 Mar](txn://${TXN}); earlier link [same row](${old}).`)
  for (const name of ["12 Mar", "same row"])
    expect((await screen.findByRole("link", { name })).getAttribute("href")).toBe(
      `/cases/${CASE}/financial?view=transactions&payment=${TXN}`
    )
  // the old link is checked like a txn:// citation
  expect(resolutions.calls[0]).toEqual([`txn://${TXN}`, old])
})

it("shows a citation whose target is not in the case as text marked so, never a link", async () => {
  resolutions.items = [{ href: `txn://${GONE}`, scheme: "txn", status: "not_in_case", reason: "Not in this case.", page_given: false, legacy: false }]
  answer(`A row [14 Mar](txn://${GONE}).`)
  expect(await screen.findByText("not in this case")).toBeVisible()
  expect(screen.queryByRole("link", { name: /14 Mar/ })).toBeNull()
  expect(screen.queryByRole("button", { name: /14 Mar/ })).toBeNull()
})

it("opens the phone record's panel beside the answer when a rec:// link is clicked (S-7)", async () => {
  const uid = "3af41de3-c6aa-4b1e-9d0e-2f4f0df3ffe5"
  resolutions.items = [ok(`rec://${uid}`, { scheme: "rec", record_uid: uid })]
  answer(`She wrote it in [C3 WhatsApp message, Tue, Mar 14, 2023](rec://${uid}).`)
  fireEvent.click(await screen.findByRole("button", { name: "C3 WhatsApp message, Tue, Mar 14, 2023" }))
  expect(await screen.findByRole("region", { name: "Record behind this message" })).toHaveTextContent(`Record ${uid}`)
  fireEvent.click(screen.getByRole("button", { name: "Close record" }))
  expect(screen.queryByRole("region", { name: "Record behind this message" })).toBeNull()
})

it("says under an answer how many citations were checked and how many are not in the case", async () => {
  const { CitationCheckLine } = await import("./AgentCitations")
  render(<CitationCheckLine check={{ total: 5, ok: 3, not_in_case: 1, ambiguous: 1, page_not_given: 2 }} />)
  expect(screen.getByTestId("citation-check").textContent).toBe(
    "5 citations checked against this case: 3 open; 1 is not in this case and is marked; 1 names a file several files share; choose one when opening; 2 document citations give no page."
  )
})
