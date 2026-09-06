import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { SourceAmountPanel } from "./SourceAmountPanel"

afterEach(() => vi.restoreAllMocks())

it("preserves canonical offsets through Chromium selection and page navigation", async () => {
  const content = "😀\r\nAmount 1234 end"
  const digest = "a".repeat(64)
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url, options) => {
      if (String(url).includes("amount-assessment")) {
        const input = JSON.parse(String(options?.body))
        return new Response(
          JSON.stringify({
            ...input,
            case_id: "case",
            evidence_file_id: "file",
            applied: false,
            offset_unit: "unicode_code_points",
            currency_source: "caller_supplied",
            limitation: "Selected text only.",
            assessment: {
              raw: input.expected_text,
              currency: input.currency,
              origin: "unknown",
              suspicion: "decimal_point_absent",
              explanation: "Review the source.",
              proposals: [
                { minor_units: "1234", basis: "Possible decimal" },
                { minor_units: "123400", basis: "Literal reading" },
              ],
            },
          })
        )
      }
      const offset = Number(
        new URL(String(url), "http://localhost").searchParams.get("start_char")
      )
      const text = offset === 0 ? "x".repeat(12000) : content
      return new Response(
        JSON.stringify({
          case_id: "case",
          evidence_file_id: "file",
          content: text,
          content_sha256: digest,
          start_char: offset,
          end_char: offset + Array.from(text).length,
          character_count: 12000 + Array.from(content).length,
          has_more: offset === 0,
          offset_unit: "unicode_code_points",
        })
      )
    })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SourceAmountPanel caseId="case" evidenceId="file" onClose={vi.fn()} />
    </QueryClientProvider>
  )
  await screen.findByLabelText("Source text")
  fireEvent.click(screen.getByRole("button", { name: "Next section" }))
  await vi.waitFor(() =>
    expect(screen.getByLabelText("Source text")).toHaveValue(
      "😀\nAmount 1234 end"
    )
  )
  const textarea = screen.getByLabelText("Source text") as HTMLTextAreaElement
  textarea.focus()
  textarea.setSelectionRange(10, 14)
  fireEvent.select(textarea)
  expect(screen.getByText("Selected: 1234")).toBeVisible()
  fireEvent.change(screen.getByLabelText("Currency (ISO code)"), {
    target: { value: "USD" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Assess selected amount" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent("12.34 USD")
  expect(screen.getByRole("status")).toHaveTextContent("1234.00 USD")
  const request = fetch.mock.calls.find(([url]) =>
    String(url).includes("amount-assessment")
  )
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({
    start_char: 12010,
    end_char: 12014,
    expected_text: "1234",
    content_sha256: digest,
    currency: "USD",
  })
  fireEvent.click(screen.getByRole("button", { name: "Previous section" }))
  expect(screen.queryByRole("status")).toBeNull()
  expect(
    screen.getByRole("button", { name: "Assess selected amount" })
  ).toBeDisabled()
})
