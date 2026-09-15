// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import {
  DuplicateDecisionForm,
  type DuplicateSelection,
} from "./DuplicateDecisionForm"

afterEach(() => vi.restoreAllMocks())
beforeEach(() => useFinancialDraftStore.setState({ drafts: {} }))
const selection: DuplicateSelection = {
  caseId: "original-case",
  document: {
    document_id: "copy",
    filename: "copy.ofx",
    revision: "a".repeat(64),
  },
  primary: {
    document_id: "kept",
    filename: "kept.ofx",
    revision: "b".repeat(64),
  },
}

it("retains duplicate reasons for matching document versions only", () => {
  const client = new QueryClient()
  const show = (selected: DuplicateSelection) => (
    <QueryClientProvider client={client}>
      <DuplicateDecisionForm selection={selected} onClose={() => {}} />
    </QueryClientProvider>
  )
  const first = render(show(selection))
  fireEvent.change(screen.getByLabelText("Reason for this decision"), {
    target: { value: "Same account, period and all twelve payments." },
  })
  first.unmount()
  const reopened = render(show(selection))
  expect(screen.getByLabelText("Reason for this decision")).toHaveValue(
    "Same account, period and all twelve payments."
  )
  reopened.rerender(
    show({
      ...selection,
      document: { ...selection.document, revision: "c".repeat(64) },
    })
  )
  expect(screen.getByLabelText("Reason for this decision")).toHaveValue("")
  reopened.rerender(show(selection))
  expect(screen.getByLabelText("Reason for this decision")).toHaveValue(
    "Same account, period and all twelve payments."
  )
})
function mount(selected = selection) {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, "invalidateQueries")
  render(
    <QueryClientProvider client={client}>
      <DuplicateDecisionForm selection={selected} onClose={vi.fn()} />
    </QueryClientProvider>
  )
  return invalidate
}
function submit() {
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Confirmed duplicate" },
  })
  fireEvent.submit(screen.getByRole("form", { name: "Duplicate decision" }))
}
it("sends one decision with reviewed revisions and invalidates its original case", async () => {
  let finish!: (value: Response) => void
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const invalidate = mount()
  submit()
  fireEvent.submit(screen.getByRole("form", { name: "Duplicate decision" }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  const [url, options] = fetch.mock.calls[0]
  expect(String(url)).toContain("case_id=original-case")
  expect(JSON.parse(String(options?.body))).toEqual({
    action: "exclude",
    reason: "Confirmed duplicate",
    primary_id: "kept",
    expected_revision: "a".repeat(64),
    expected_primary_revision: "b".repeat(64),
  })
  finish(
    new Response(
      JSON.stringify({
        case_id: "original-case",
        document_id: "copy",
        action: "exclude",
        applied: true,
        changed_rows: 2,
        adjudication_id: "event",
      })
    )
  )
  expect(await screen.findByRole("status")).toHaveTextContent("2 rows excluded")
  expect(screen.queryByRole("button", { name: "Record decision" })).toBeNull()
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-decisions", "original-case"],
  })
})
it.each([409, 500, 200])(
  "does not call an unconfirmed response success or retry it (%s)",
  async (status) => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify(
              status === 200 ? { applied: false } : { detail: "Changed" }
            ),
            { status }
          )
      )
    mount()
    submit()
    expect(await screen.findByRole("alert")).toHaveTextContent(
      status === 409 ? "Decision refused" : "may have been recorded"
    )
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: "Record decision" })).toBeNull()
  }
)
it("restoration sends no primary and explains the effect on totals", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(JSON.stringify({ detail: "Legacy exclusion" }), {
        status: 409,
      })
  )
  mount({ ...selection, primary: undefined })
  expect(screen.getByText(/Both copies may then count/)).toBeInTheDocument()
  submit()
  await screen.findByRole("alert")
  const body = JSON.parse(String(fetch.mock.calls[0][1]?.body))
  expect(body.action).toBe("restore")
  expect(body).not.toHaveProperty("primary_id")
})

it("refreshes previously opened payment sources and analysis lists after a duplicate decision", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: 120000 } },
  })
  const prefixes = [
    "ledger-source",
    "financial-linked-payments",
    "financial-proof-standing",
    "statement-import-status",
  ]
  for (const prefix of prefixes) {
    client.setQueryData([prefix, selection.caseId, "prior-view"], {
      status: "admitted",
    })
    client.setQueryData([prefix, "another-case", "prior-view"], {
      status: "admitted",
    })
  }
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(
        JSON.stringify({
          case_id: selection.caseId,
          document_id: "copy",
          action: "exclude",
          applied: true,
          changed_rows: 2,
          adjudication_id: "event",
        })
      )
  )
  render(
    <QueryClientProvider client={client}>
      <DuplicateDecisionForm selection={selection} onClose={vi.fn()} />
    </QueryClientProvider>
  )
  submit()
  await screen.findByRole("status")
  for (const prefix of prefixes) {
    expect(
      client.getQueryState([prefix, selection.caseId, "prior-view"])
        ?.isInvalidated
    ).toBe(true)
    expect(
      client.getQueryState([prefix, "another-case", "prior-view"])
        ?.isInvalidated
    ).toBe(false)
  }
})
