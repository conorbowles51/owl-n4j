import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { StatementControlPicker } from "./StatementControlPicker"
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: ({
    locatorPayload,
  }: {
    locatorPayload: unknown
  }) => <p data-testid="control-locator">{JSON.stringify(locatorPayload)}</p>,
}))
afterEach(() => vi.restoreAllMocks())
const answer = {
  case_id: "case",
  evidence_file_id: "file",
  page_number: 1,
  table_index: 0,
  table_count: 1,
  source_revision: "a".repeat(64),
  locator: { page: 1 },
  applied: false,
  rows: [
    {
      row_index: 3,
      cells: [
        {
          column_index: 2,
          expected_text: "Opening 100.00",
          locator: { page: 1, rect: [1, 2, 3, 4] },
        },
      ],
    },
  ],
}
function mount(data: unknown = answer) {
  const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => new Response(JSON.stringify(data))),
    selected = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <StatementControlPicker
        caseId="case"
        fileId="file"
        label="opening balance"
        onSelected={selected}
        onClose={vi.fn()}
      />
    </QueryClientProvider>
  )
  return { fetch, selected }
}
it("highlights the original cell before explicitly using its unchanged binding", async () => {
  const { fetch, selected } = mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Control row 4, column 3" })
  )
  expect(selected).not.toHaveBeenCalled()
  expect(screen.getByTestId("control-locator")).toHaveTextContent(
    '"rect":[1,2,3,4]'
  )
  fireEvent.click(screen.getByRole("button", { name: "Use this control cell" }))
  expect(selected).toHaveBeenCalledWith({
    page_number: 1,
    table_index: 0,
    row_index: 3,
    column_index: 2,
    source_revision: "a".repeat(64),
    expected_text: "Opening 100.00",
  })
  expect(
    fetch.mock.calls.every(
      ([, options]) => !options?.method || options.method === "GET"
    )
  ).toBe(true)
})
it.each([
  { case_id: "other" },
  { evidence_file_id: "other" },
  { page_number: 2 },
  { table_index: 1 },
  { applied: true },
])("refuses mismatched control source %j", async (change) => {
  mount({ ...answer, ...change })
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Control source unavailable"
  )
  expect(
    screen.queryByRole("button", { name: "Use this control cell" })
  ).not.toBeInTheDocument()
})
it("clears a selected control when a new page cannot be loaded", async () => {
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Control row 4, column 3" })
  )
  fireEvent.change(screen.getByLabelText("Statement control source page"), {
    target: { value: "2" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Load control page" }))
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Use this control cell" })
    ).not.toBeInTheDocument()
  )
  expect(await screen.findByRole("alert")).toBeVisible()
})
