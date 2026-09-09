import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateSourcePicker } from "./CandidateSourcePicker"
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: ({
    locatorPayload,
  }: {
    locatorPayload: unknown
  }) => <p data-testid="source-locator">{JSON.stringify(locatorPayload)}</p>,
}))
afterEach(() => vi.restoreAllMocks())
const table = {
  case_id: "case-a",
  evidence_file_id: "file-a",
  page_number: 1,
  table_index: 0,
  table_count: 1,
  source_revision: "a".repeat(64),
  table_source: "text_alignment",
  geometry_source: "cell_rectangles",
  locator: {},
  columns: [0, 1],
  rows: [
    {
      row_index: 0,
      cells: [
        { column_index: 0, expected_text: "Date", locator: {} },
        { column_index: 1, expected_text: "Amount", locator: {} },
      ],
    },
    {
      row_index: 3,
      cells: [
        { column_index: 0, expected_text: "01/02", locator: {} },
        {
          column_index: 1,
          expected_text: "1234",
          locator: { kind: "page_rectangle", page: 1, rect: [10, 20, 30, 40] },
        },
      ],
    },
  ],
  applied: false,
}
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}
function server({
  wrongCase = false,
  stale = false,
  wrongEcho = false,
  wrongPage = false,
} = {}) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url, options) => {
      if (options?.method === "POST") {
        if (stale)
          return json({ detail: "Source changed. Rebuild mapping." }, 409)
        const proposal = JSON.parse(String(options.body))
        return json({
          id: "mapping-a",
          case_id: "case-a",
          evidence_file_id: "file-a",
          mapping_revision: "b".repeat(64),
          original: {
            proposal: {
              ...proposal,
              source_revision: wrongEcho
                ? "c".repeat(64)
                : proposal.source_revision,
            },
          },
          applied: false,
          candidates: proposal.rows.map(
            (r: {
              row_index: number
              cells: { column_index: number; expected_text: string }[]
            }) => ({
              id: `candidate-${r.row_index}`,
              row_index: r.row_index,
              status: "pending",
              original: {
                cells: r.cells.map((c) => ({
                  column_index: c.column_index,
                  proposed_meaning: "unknown",
                  text: c.expected_text,
                })),
              },
            })
          ),
        })
      }
      if (String(url).includes("/pages/"))
        return json({
          ...table,
          case_id: wrongCase ? "case-b" : "case-a",
          page_number: wrongPage ? 2 : 1,
        })
      return json({
        case_id: "case-a",
        offset: 0,
        has_more: false,
        items: [
          {
            evidence_file_id: "file-a",
            filename: "Synthetic.pdf",
            page_number: 1,
          },
        ],
      })
    })
}
function mount(onSaved = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={client}>
      <CandidateSourcePicker caseId="case-a" onSaved={onSaved} />
    </QueryClientProvider>
  )
  return { ...view, client, onSaved }
}
async function open() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Synthetic.pdf · page 1" })
  )
}
async function choose() {
  await open()
  fireEvent.click(await screen.findByLabelText("Select source row 4"))
}
it("starts with no nominated transactions or assigned meanings", async () => {
  const fetch = server()
  mount()
  await open()
  expect(await screen.findByLabelText("Column 1 meaning")).toHaveValue(
    "unknown"
  )
  expect(screen.getByLabelText("Select source row 4")).not.toBeChecked()
  expect(
    screen.getByRole("button", { name: "Save selected rows for review" })
  ).toBeDisabled()
  expect(screen.getByText(/Rows inferred from text spacing/)).toBeVisible()
  expect(fetch.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    0
  )
})
it("saves exact selected coordinates/text and deliberate meanings only once", async () => {
  const fetch = server()
  const { onSaved } = mount()
  await choose()
  fireEvent.change(screen.getByLabelText("Column 2 meaning"), {
    target: { value: "amount" },
  })
  const button = screen.getByRole("button", {
    name: "Save selected rows for review",
  })
  fireEvent.click(button)
  fireEvent.click(button)
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith("mapping-a"))
  const writes = fetch.mock.calls.filter(([, o]) => o?.method === "POST")
  expect(writes).toHaveLength(1)
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({
    schema_version: "pdf-grid-mapping-v1",
    case_id: "case-a",
    evidence_file_id: "file-a",
    page_number: 1,
    table_index: 0,
    source_revision: "a".repeat(64),
    columns: [
      { column_index: 0, meaning: "unknown" },
      { column_index: 1, meaning: "amount" },
    ],
    rows: [
      {
        row_index: 3,
        cells: [
          { column_index: 0, expected_text: "01/02" },
          { column_index: 1, expected_text: "1234" },
        ],
      },
    ],
  })
  expect(button).toBeDisabled()
})
it("blocks stale or uncertain writes until an explicit reload resets selection", async () => {
  server({ stale: true })
  mount()
  await choose()
  fireEvent.click(
    screen.getByRole("button", { name: "Save selected rows for review" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("Source changed")
  expect(screen.getByLabelText("Select source row 4")).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Reload source and selection" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Select source row 4")).toBeEnabled()
  )
  expect(screen.getByLabelText("Select source row 4")).not.toBeChecked()
})
it("refuses an echoed mapping from a different revision", async () => {
  server({ wrongEcho: true })
  const { onSaved } = mount()
  await choose()
  fireEvent.click(
    screen.getByRole("button", { name: "Save selected rows for review" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "does not match your selection"
  )
  expect(onSaved).not.toHaveBeenCalled()
})
it("refuses wrong-case source content", async () => {
  server({ wrongCase: true })
  mount()
  await open()
  expect(await screen.findByRole("alert")).toBeVisible()
  expect(screen.queryByLabelText("Select source row 4")).not.toBeInTheDocument()
})
it("refuses the wrong page even in the right case", async () => {
  server({ wrongPage: true })
  mount()
  await open()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "selected PDF table"
  )
})
it("invalidates the original case list after an unmounted save", async () => {
  const fetch = server()
  const { client, unmount } = mount()
  const invalidate = vi.spyOn(client, "invalidateQueries")
  await choose()
  const response = fetch.getMockImplementation()!
  let release!: () => void
  fetch.mockImplementation(async (url, options) => {
    if (options?.method === "POST")
      await new Promise<void>((resolve) => {
        release = resolve
      })
    return response(url, options)
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save selected rows for review" })
  )
  await waitFor(() => expect(release).toBeDefined())
  unmount()
  release()
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["financial-candidates", "case-a", "list"],
    })
  )
})

it("offers exact header suggestions without assigning meanings or selecting rows", async () => {
  const fetch = server()
  mount()
  await open()
  fireEvent.click(
    await screen.findByRole("button", { name: "Suggest column meanings" })
  )
  expect(
    screen.getByText(/Generic “Date” does not establish/)
  ).toBeInTheDocument()
  expect(screen.getByLabelText("Column 2 meaning")).toHaveValue("unknown")
  fireEvent.click(
    screen.getByRole("button", { name: "Use Amount for column 2" })
  )
  expect(screen.getByLabelText("Column 2 meaning")).toHaveValue("amount")
  expect(screen.getByLabelText("Column 1 meaning")).toHaveValue("unknown")
  expect(screen.getByLabelText("Select source row 1")).not.toBeChecked()
  expect(screen.getByLabelText("Select source row 4")).not.toBeChecked()
  expect(fetch.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    0
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Reload source and selection" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Column 2 meaning")).toHaveValue("unknown")
  )
})
it("saves an explicitly chosen transaction date role separately from booking date", async () => {
  const fetch = server()
  mount()
  await choose()
  fireEvent.change(screen.getByLabelText("Column 1 meaning"), {
    target: { value: "transaction_date" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save selected rows for review" })
  )
  await screen.findByText(/Rows saved/)
  const request = fetch.mock.calls.find(([, o]) => o?.method === "POST")!
  expect(JSON.parse(String(request[1]?.body)).columns[0].meaning).toBe(
    "transaction_date"
  )
})

it("locates a cell without nominating or saving its row and resets on source reload", async () => {
  const fetch = server()
  mount()
  await open()
  const cell = await screen.findByRole("button", {
    name: "Show source row 4, column 2",
  })
  fireEvent.click(cell)
  expect(cell).toHaveAttribute("aria-pressed", "true")
  expect(screen.getByTestId("source-locator")).toHaveTextContent(
    JSON.stringify(table.rows[1].cells[1].locator)
  )
  expect(screen.getByLabelText("Select source row 4")).not.toBeChecked()
  expect(
    screen.getByRole("button", { name: "Save selected rows for review" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Show table location" }))
  expect(screen.getByTestId("source-locator")).toHaveTextContent("{}")
  fireEvent.click(cell)
  fireEvent.click(
    screen.getByRole("button", { name: "Reload source and selection" })
  )
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Show table location" })
    ).not.toBeInTheDocument()
  )
  expect(fetch.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    0
  )
})
