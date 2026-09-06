import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { SourceAmountPanel } from "./SourceAmountPanel"
import { sourceSelection } from "../lib/source-selection"

afterEach(() => vi.restoreAllMocks())
const content = "😀\r\nAmount 1234 end"
const windowData = {
  case_id: "case",
  evidence_file_id: "file",
  content,
  content_sha256: "a".repeat(64),
  start_char: 0,
  end_char: Array.from(content).length,
  character_count: Array.from(content).length,
  has_more: false,
  offset_unit: "unicode_code_points",
}
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status })
}
function mount() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SourceAmountPanel caseId="case" evidenceId="file" onClose={vi.fn()} />
    </QueryClientProvider>
  )
}
it("maps textarea newlines and UTF-16 positions to unchanged source code points", () => {
  expect(sourceSelection(content, 10, 14)).toEqual({
    start: 10,
    end: 14,
    text: "1234",
  })
  expect(sourceSelection("😀1234", 2, 6)).toEqual({
    start: 1,
    end: 5,
    text: "1234",
  })
  expect(sourceSelection("😀1234", 1, 6)).toBeNull()
  expect(sourceSelection("a".repeat(129), 0, 129)).toBeNull()
  expect(sourceSelection("x\ry", 2, 3)).toEqual({ start: 2, end: 3, text: "y" })
})
it("assesses the selected source and clears the result when currency changes", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(windowData))
    .mockResolvedValueOnce(
      response({
        case_id: "case",
        evidence_file_id: "file",
        content_sha256: "a".repeat(64),
        start_char: 10,
        end_char: 14,
        applied: false,
        offset_unit: "unicode_code_points",
        currency_source: "caller_supplied",
        limitation: "Selected text only.",
        assessment: {
          raw: "1234",
          currency: "USD",
          origin: "unknown",
          suspicion: "missing_separator",
          explanation: "Review the source.",
          proposals: [{ minor_units: "1234", basis: "Possible decimal" }],
        },
      })
    )
  mount()
  const text = await screen.findByLabelText("Source text")
  fireEvent.select(text, { target: { selectionStart: 10, selectionEnd: 14 } })
  fireEvent.change(screen.getByLabelText("Currency (ISO code)"), {
    target: { value: "usd" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Assess selected amount" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent("12.34 USD")
  expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({
    start_char: 10,
    end_char: 14,
    expected_text: "1234",
    content_sha256: "a".repeat(64),
    currency: "USD",
  })
  fireEvent.change(screen.getByLabelText("Currency (ISO code)"), {
    target: { value: "GBP" },
  })
  expect(screen.queryByRole("status")).toBeNull()
})
it("refuses a source window for another case", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    response({ ...windowData, case_id: "other" })
  )
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent("inconsistent")
  expect(screen.queryByLabelText("Source text")).toBeNull()
})
