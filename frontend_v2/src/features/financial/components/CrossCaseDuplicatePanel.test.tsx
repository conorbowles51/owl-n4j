import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CrossCaseDuplicatePanel } from "./CrossCaseDuplicatePanel"
afterEach(() => vi.restoreAllMocks())
const match = {
  case_id: "a",
  comparison_case_id: "b",
  applied: false,
  documents: { a: 1, b: 1 },
  compared: { a: 1, b: 1 },
  stored_rows_checked: 4,
  limitation: "No ledger changes.",
  skipped: [],
  matches: [
    {
      left: {
        case_id: "a",
        document_id: "one",
        filename: "First.pdf",
        status: "admitted",
      },
      right: {
        case_id: "b",
        document_id: "two",
        filename: "Second.pdf",
        status: "admitted",
      },
      matching_ingestion_hash: true,
      matching_stored_reading: false,
    },
  ],
}
function mount(data = match) {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
    async (url) =>
      new Response(
        JSON.stringify(
          String(url).includes("/api/cases")
            ? {
                cases: [
                  { id: "a", title: "Current" },
                  { id: "b", title: "Other case" },
                ],
              }
            : data
        )
      )
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CrossCaseDuplicatePanel caseId="a" />
    </QueryClientProvider>
  )
  return fetch
}
it("requires explicit other-case selection and displays match basis without exclusion controls", async () => {
  const fetch = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Choose comparison case" })
  )
  await screen.findByRole("option", { name: "Other case" })
  expect(
    screen.queryByRole("option", { name: "Current" })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Comparison case"), {
    target: { value: "b" },
  })
  expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent.click(
    screen.getByRole("button", { name: "Compare selected cases" })
  )
  await screen.findByText(/First.pdf ↔ Second.pdf/)
  expect(
    screen.getByText(/Stored readings are not established as equal/)
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: /Exclude/ })
  ).not.toBeInTheDocument()
})
it("rejects a response whose other-case membership differs", async () => {
  mount({ ...match, comparison_case_id: "secret" })
  fireEvent.click(
    screen.getByRole("button", { name: "Choose comparison case" })
  )
  await screen.findByRole("option", { name: "Other case" })
  fireEvent.change(screen.getByLabelText("Comparison case"), {
    target: { value: "b" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Compare selected cases" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("different scope")
  expect(screen.queryByText(/First.pdf/)).not.toBeInTheDocument()
})
