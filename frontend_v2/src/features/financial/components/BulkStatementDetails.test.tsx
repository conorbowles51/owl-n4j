import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { BulkStatementDetails } from "./BulkStatementDetails"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const items = Array.from({ length: 52 }, (_, i) => ({
  key: `item-${i}`,
  file_id: `file-${i}`,
  source_id: i % 2 ? null : `source-${i}`,
  statement_id: null,
  revision: "a".repeat(64),
  filename: `Statement ${i}.pdf`,
  status: i % 2 ? "Not imported" : "Imported",
  values: {
    holder: "",
    account_number: `000${i}`,
    institution: "Example Bank",
    currency: "MXN",
    period_start: "2026-01-01",
    period_end: "2026-01-31",
  },
}))
type Body = {
  targets: typeof items
  changes: Record<string, string>
  mode: string
  request_id: string
  preview_revision?: string
}
let sent: { url: string; body: Body }[],
  failSave = false
beforeEach(() => {
  vi.resetAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
  sent = []
  failSave = false
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const body = options?.body as Body
    sent.push({ url, body })
    if (url.includes("/statements?"))
      return { case_id: "case", items, notices: [] } as never
    if (url.includes("/preview?"))
      return {
        case_id: "case",
        preview_revision: "b".repeat(64),
        updated: body.targets.length,
        items: body.targets.map((target) => ({
          ...items.find((item) => item.file_id === target.file_id)!,
          after: body.changes,
          changes: Object.fromEntries(
            Object.entries(body.changes).map(([key, value]) => [
              key,
              { before: "", after: value },
            ])
          ),
        })),
      } as never
    if (failSave) {
      failSave = false
      throw Error("Connection interrupted")
    }
    return {
      case_id: "case",
      updated: body.targets.length,
      unchanged: 0,
      imported: 26,
      drafts: 26,
      account_changes: [],
      items: [],
    } as never
  })
})
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BulkStatementDetails caseId="case" batchId="batch" onSaved={vi.fn()} />
    </QueryClientProvider>
  )
}
async function choose() {
  fireEvent.click(screen.getByRole("button", { name: "Edit account details" }))
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Select all 52 matching statements",
    })
  )
  fireEvent.click(screen.getByLabelText("Change account holder"))
  fireEvent.change(screen.getByLabelText("New account holder"), {
    target: { value: "Example Company" },
  })
}
it("selects across pages, previews only opted-in fields, and distinguishes saved imports from drafts", async () => {
  mount()
  await choose()
  expect(screen.getByLabelText("How to apply account details")).toHaveValue(
    "fill_missing"
  )
  fireEvent.change(
    screen.getByLabelText("Find statements for account details"),
    { target: { value: "Statement 51.pdf" } }
  )
  expect(screen.getByText("52 selected · 51 hidden by search")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Review changes for 52 statements" })
  )
  fireEvent.click(
    await screen.findByRole("button", { name: "Save changes to 52 statements" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent(
    "26 imported statements updated; 26 saved for later import"
  )
  const save = sent.find((call) => call.url.includes("/save?"))!.body
  expect(save.targets).toHaveLength(52)
  expect(save.changes).toEqual({ holder: "Example Company" })
  expect(save.preview_revision).toBe("b".repeat(64))
  expect(save.mode).toBe("fill_missing")
})
it("keeps draft selection and fields when closed, reopened and remounted", async () => {
  const view = mount()
  await choose()
  fireEvent.click(screen.getByRole("button", { name: "Close — keep draft" }))
  view.unmount()
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Edit account details" }))
  expect(await screen.findByLabelText("New account holder")).toHaveValue(
    "Example Company"
  )
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Review changes for 52 statements" })
    ).toBeEnabled()
  )
})
it("retries a lost save response with the identical request and preview, and retains choices on errors", async () => {
  failSave = true
  mount()
  await choose()
  fireEvent.click(
    screen.getByRole("button", { name: "Review changes for 52 statements" })
  )
  fireEvent.click(
    await screen.findByRole("button", { name: "Save changes to 52 statements" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your selection and edits are kept"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Save changes to 52 statements" })
  )
  await screen.findByRole("status")
  const attempts = sent.filter((call) => call.url.includes("/save?"))
  expect(attempts).toHaveLength(2)
  expect(attempts[0].body).toEqual(attempts[1].body)
})
it("requires opt-in to replace existing values and refreshes stale selection without losing field edits", async () => {
  mount()
  await choose()
  fireEvent.change(screen.getByLabelText("How to apply account details"), {
    target: { value: "replace" },
  })
  fireEvent.click(screen.getByLabelText("Change account number"))
  fireEvent.change(screen.getByLabelText("New account number"), {
    target: { value: "0012345" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Refresh statements" }))
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Review changes for 52 statements" })
    ).toBeEnabled()
  )
  expect(screen.getByLabelText("New account number")).toHaveValue("0012345")
  expect(screen.getByLabelText("New account holder")).toHaveValue(
    "Example Company"
  )
})
it("rejects another case list", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "another",
    items,
    notices: [],
  } as never)
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Edit account details" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
})

it("sets an explicit month, retains custom dates and previews dates only", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BulkStatementDetails
        caseId="case"
        batchId="batch"
        datesOnly
        onSaved={vi.fn()}
      />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Set dates for selected statements" })
  )
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Select all 52 matching statements",
    })
  )
  fireEvent.change(screen.getByLabelText("Statement month and year"), {
    target: { value: "2024-02" },
  })
  expect(screen.getByLabelText("New statement start date")).toHaveValue(
    "2024-02-01"
  )
  expect(screen.getByLabelText("New statement end date")).toHaveValue(
    "2024-02-29"
  )
  fireEvent.change(screen.getByLabelText("New statement start date"), {
    target: { value: "2024-02-05" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Review changes for 52 statements" })
  )
  await screen.findByRole("button", { name: "Save changes to 52 statements" })
  expect(sent.find((c) => c.url.includes("/preview?"))!.body.changes).toEqual({
    period_start: "2024-02-05",
    period_end: "2024-02-29",
  })
  expect(sent.some((c) => c.url.includes("/save?"))).toBe(false)
})
it("says when loading the statement periods ran past the time limit and offers to try again", async () => {
  let calls = 0
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("/statements?") && calls++ === 0)
      throw new DOMException("signal is aborted without reason", "AbortError")
    return { case_id: "case", items, notices: [] } as never
  })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Edit account details" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "took longer than the 5-minute limit and was stopped. Nothing was changed."
  )
  fireEvent.click(screen.getByRole("button", { name: "Try again" }))
  expect(
    await screen.findByRole("button", { name: "Select all 52 matching statements" })
  ).toBeInTheDocument()
  expect(calls).toBe(2)
})

it("offers one shared proposal for a missing detail, with its source", async () => {
  const { commonProposal } = await import("../lib/common-proposal")
  const usd = { value: "USD", basis: "case_default", label: "the case's usual currency (9 of 9 saved statements)", confirmed: false }
  const statement = (currency: string, proposal?: typeof usd) => ({
    ...items[1],
    values: { ...items[1].values, currency },
    proposals: proposal ? { currency: proposal } : undefined,
  })
  expect(commonProposal([statement("", usd), statement("", usd), statement("MXN")], "currency")).toEqual({
    value: "USD",
    label: usd.label,
    statements: 2,
  })
  // A statement without a proposal, or two different values: nothing is proposed.
  expect(commonProposal([statement("", usd), statement("")], "currency")).toBeNull()
  expect(commonProposal([statement("", usd), statement("", { ...usd, value: "EUR" })], "currency")).toBeNull()
  expect(commonProposal([statement("MXN")], "currency")).toBeNull()
})
it("when a save finds a statement read again, previews it as it reads now and asks only about a moved field", async () => {
  let saves = 0
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const body = options?.body as Body & { read_current?: boolean }
    if (url.includes("/save?") && !saves++) {
      sent.push({ url, body })
      throw Object.assign(Error("A selected statement was read again since this preview."), { status: 409 })
    }
    if (url.includes("/preview?") && body.read_current) {
      sent.push({ url, body })
      const first = { ...items[1], after: { ...items[1].values, holder: "Reading Co" } }
      return {
        case_id: "case", preview_revision: "c".repeat(64), updated: 0,
        items: [{ ...first, changes: {}, refreshed: { holder: { listed: "", current: "Reading Co" } }, conflicts: ["holder"] }],
      } as never
    }
    return base(url, options)
  })
  mount()
  await choose()
  fireEvent.click(screen.getByRole("button", { name: "Review changes for 52 statements" }))
  fireEvent.click(await screen.findByRole("button", { name: "Save changes to 52 statements" }))
  // No refusal: the current preview comes back with the one field to choose.
  expect(await screen.findByText(/Updated to the latest reading/)).toBeVisible()
  expect(screen.getByRole("group", { name: "Choose Account holder" })).toHaveTextContent(
    "the statement now reads Reading Co. You entered Example Company."
  )
  expect(screen.getByRole("button", { name: "Choose a value above to save" })).toBeDisabled()
  expect(screen.queryByText(/Open it individually|check its batch again/)).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Use Example Company" }))
  await waitFor(() => {
    const last = sent.filter((call) => call.url.includes("/preview?")).at(-1)!.body
    expect(last.mode).toBe("replace")
    expect((last as { read_current?: boolean }).read_current).toBe(true)
  })
})
