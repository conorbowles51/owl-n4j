import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { FinancialFindings } from "./FinancialFindings"
import { FinancialReportsList } from "./FinancialReportsList"

const list = vi.hoisted(() => vi.fn())
vi.mock("@/features/workspace/casework-api", () => ({ caseworkAPI: { list } }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./FinancialReportBuilder", () => ({
  FinancialReportBuilder: () => null,
}))
vi.mock("./SavedFinancialReport", () => ({ SavedFinancialReport: () => null }))
vi.mock("./FindingReportBundle", () => ({ FindingReportBundle: () => null }))
function result(
  caseId: string,
  params: { offset?: number; tag?: string; q?: string }
) {
  return {
    total: 61,
    entries: [
      {
        id: `${caseId}-${params.offset ?? 0}`,
        case_id: caseId,
        title: `Saved item ${params.offset ?? 0}`,
        tags: [params.tag],
        links: [],
        body: "Synthetic note",
        entry_type: "note",
        version: 1,
      },
    ],
  }
}
function setup(kind: "findings" | "reports", caseId = "case-one") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const component = (id: string) => (
    <QueryClientProvider client={client}>
      {kind === "findings" ? (
        <FinancialFindings caseId={id} />
      ) : (
        <FinancialReportsList caseId={id} />
      )}
    </QueryClientProvider>
  )
  const mounted = render(component(caseId))
  return {
    ...mounted,
    changeCase: (id: string) => mounted.rerender(component(id)),
  }
}
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  useAuthStore.setState({ user: null })
  list
    .mockReset()
    .mockImplementation(async (caseId, params) => result(caseId, params))
})
it("restores saved-work search, page and report selection after remount", async () => {
  const first = setup("findings")
  await screen.findByRole("heading", { name: "Saved item 0" })
  fireEvent.change(screen.getByLabelText("Search saved work"), {
    target: { value: "supplier" },
  })
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Next notes" })).toBeEnabled()
  )
  fireEvent.click(screen.getByRole("button", { name: "Next notes" }))
  await screen.findByRole("heading", { name: "Saved item 25" })
  fireEvent.click(screen.getByLabelText("Include Saved item 25 in report"))
  first.unmount()
  const second = setup("findings")
  await screen.findByRole("heading", { name: "Saved item 25" })
  expect(screen.getByLabelText("Search saved work")).toHaveValue("supplier")
  expect(screen.getByLabelText("Include Saved item 25 in report")).toBeChecked()
  second.changeCase("case-two")
  expect(screen.getByLabelText("Search saved work")).toHaveValue("")
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith(
      "case-two",
      expect.objectContaining({ q: "", offset: 0 })
    )
  )
  second.changeCase("case-one")
  expect(screen.getByLabelText("Search saved work")).toHaveValue("supplier")
  act(() => useAuthStore.setState({ user: { id: "another-member" } as never }))
  expect(screen.getByLabelText("Search saved work")).toHaveValue("")
})
it("retries failed finding searches without losing the search or page", async () => {
  list.mockRejectedValueOnce(Error("Connection interrupted"))
  useFinancialDraftStore
    .getState()
    .put("anonymous:case-one:findings-list", { search: "supplier", page: 1 })
  setup("findings")
  await screen.findByRole("alert")
  expect(screen.getByLabelText("Search saved work")).toHaveValue("supplier")
  fireEvent.click(
    screen.getByRole("button", { name: "Try loading saved work again" })
  )
  await screen.findByRole("heading", { name: "Saved item 25" })
  expect(list).toHaveBeenLastCalledWith(
    "case-one",
    expect.objectContaining({ q: "supplier", offset: 25 })
  )
  expect(screen.queryByRole("alert")).toBeNull()
})
it("does not skip notes or select stale search results while the next page loads", async () => {
  setup("findings")
  await screen.findByRole("heading", { name: "Saved item 0" })
  let finish!: (value: unknown) => void
  list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  fireEvent.click(screen.getByRole("button", { name: "Next notes" }))
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Next notes" })).toBeDisabled()
  )
  expect(screen.getByRole("button", { name: "Previous notes" })).toBeDisabled()
  expect(screen.getByLabelText("Include Saved item 0 in report")).toBeDisabled()
  await act(async () =>
    finish(result("case-one", { offset: 25, tag: "financial" }))
  )
  await screen.findByRole("heading", { name: "Saved item 25" })
})
it("retains the saved-report page separately for each case and user", async () => {
  const first = setup("reports")
  await screen.findByRole("heading", { name: "Saved item 0" })
  fireEvent.click(
    screen.getByRole("button", { name: "Next financial reports" })
  )
  await screen.findByRole("heading", { name: "Saved item 25" })
  first.unmount()
  const second = setup("reports")
  await screen.findByRole("heading", { name: "Saved item 25" })
  second.changeCase("case-two")
  await screen.findByRole("heading", { name: "Saved item 0" })
  second.changeCase("case-one")
  await screen.findByRole("heading", { name: "Saved item 25" })
  act(() => useAuthStore.setState({ user: { id: "another-member" } as never }))
  await screen.findByRole("heading", { name: "Saved item 0" })
})
it("retries a failed report page without returning to the first page", async () => {
  list.mockRejectedValueOnce(Error("Connection interrupted"))
  useFinancialDraftStore
    .getState()
    .put("anonymous:case-one:financial-reports-page", 1)
  setup("reports")
  await screen.findByRole("alert")
  fireEvent.click(
    screen.getByRole("button", { name: "Try loading reports again" })
  )
  await screen.findByRole("heading", { name: "Saved item 25" })
  expect(list).toHaveBeenLastCalledWith(
    "case-one",
    expect.objectContaining({ offset: 25, tag: "financial-report" })
  )
})

it("keeps findings compact while preserving expansion, filters and report selection", async () => {
  const first = setup("findings")
  const title = await screen.findByRole("button", { name: "Saved item 0" })
  expect(title).toHaveAttribute("aria-expanded", "false")
  expect(screen.queryByText("Synthetic note")).toBeNull()
  expect(screen.getByRole("button", { name: "Edit" })).toBeVisible()
  expect(screen.getByRole("button", { name: "Add to Timeline" })).toBeVisible()
  fireEvent.click(screen.getByLabelText("Include Saved item 0 in report"))
  fireEvent.click(title)
  expect(screen.getByText("Synthetic note")).toBeVisible()
  first.unmount()
  const second = setup("findings")
  expect(
    await screen.findByRole("button", { name: "Saved item 0" })
  ).toHaveAttribute("aria-expanded", "true")
  expect(screen.getByLabelText("Include Saved item 0 in report")).toBeChecked()
  fireEvent.change(screen.getByLabelText("Finding type"), {
    target: { value: "financial-question" },
  })
  fireEvent.change(screen.getByLabelText("Progress"), {
    target: { value: "in-progress" },
  })
  second.unmount()
  setup("findings")
  expect(screen.getByLabelText("Finding type")).toHaveValue(
    "financial-question"
  )
  expect(screen.getByLabelText("Progress")).toHaveValue("in-progress")
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith(
      "case-one",
      expect.objectContaining({ tag: "financial-question-in-progress" })
    )
  )
})

it("renders existing saved narrative as formatted text and omits empty follow-up sections", async () => {
  const data = result("case-one", { tag: "financial" })
  data.entries[0].tags = ["financial", "financial-workspace"]
  data.entries[0].body =
    "## Evidence reviewed\nThe **original** record supports this.\n\n- Check the reference\n- Compare dates\n\n## Next action\n\n\n## Assigned to"
  list.mockResolvedValue(data)
  setup("findings")
  fireEvent.click(await screen.findByRole("button", { name: "Saved item 0" }))
  expect(
    screen.getByRole("heading", { name: "Evidence reviewed" })
  ).toBeVisible()
  expect(screen.getByText("original").tagName).toBe("STRONG")
  expect(screen.getAllByRole("listitem")).toHaveLength(2)
  expect(screen.queryByText(/##/)).toBeNull()
  expect(screen.queryByText("Next action")).toBeNull()
  expect(screen.queryByText("Assigned to")).toBeNull()
})
