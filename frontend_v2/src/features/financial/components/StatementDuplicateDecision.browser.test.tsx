import "@/styles/globals.css"
import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { StatementDuplicateDecision } from "./StatementDuplicateDecision"
import type { StatementDuplicateDisposition } from "../lib/statement-duplicate"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: ({
    documentName,
    initialPage,
    onOpenChange,
  }: {
    documentName: string
    initialPage: number
    onOpenChange: (open: boolean) => void
  }) => (
    <div
      role="dialog"
      aria-label="Retained original"
      className="rounded border bg-background p-4"
    >
      {documentName} · Page {initialPage}
      <button onClick={() => onOpenChange(false)}>Close original</button>
    </div>
  ),
}))
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})
const caseId = "10000000-0000-4000-8000-000000000001"
const fileId = "10000000-0000-4000-8000-000000000002"
const revision = "a".repeat(64)
const initial: StatementDuplicateDisposition = {
  policy: "pending-statement-duplicate-v1",
  reading_revision: revision,
  revision,
  status: "ignored",
  label: "Duplicate - Ignored by system",
  current: true,
  reason:
    "The full statement identity and financial reading match the retained source. Evidence and saved reviews remain available.",
  matched_fields: [
    "bank",
    "full_account_number",
    "account_holder",
    "period_start",
    "period_end",
    "currency",
    "account_type",
  ],
  basis: "identical_financial_reading",
  retained: {
    evidence_file_id: "10000000-0000-4000-8000-000000000003",
    filename:
      "Synthetic retained monthly bank statement with the investigator’s existing corrections.pdf",
    page_number: 5,
  },
}
function Harness() {
  const [decision, update] = useState(initial)
  return (
    <main className="mx-auto max-w-4xl p-4">
      <h1 className="mb-3 text-lg font-semibold">
        Review synthetic January statement
      </h1>
      <StatementDuplicateDecision
        caseId={caseId}
        fileId={fileId}
        readingRevision={revision}
        currency="USD"
        decision={decision}
        canEdit
        onDecision={update}
      />
    </main>
  )
}
it("keeps the duplicate decision, source and restore action usable at wide and narrow widths", async () => {
  await page.viewport(1440, 1000)
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: caseId,
    evidence_file_id: fileId,
    statement_id: null,
    duplicate_disposition: {
      ...initial,
      revision: "b".repeat(64),
      status: "restored",
      label: "Restored for review",
      reason: "Compare the extra source page.",
    },
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Harness />
    </QueryClientProvider>
  )
  expect(fetchAPI).not.toHaveBeenCalled()
  expect(
    screen.getByRole("heading", { name: "Duplicate - Ignored by system" })
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Open retained original" })
  )
  expect(screen.getByRole("dialog")).toHaveTextContent("Page 5")
  fireEvent.click(screen.getByRole("button", { name: "Close original" }))
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  await page.screenshot({
    path: "/private/tmp/loupe-duplicate-decision-wide.png",
    element: screen.getByRole("main"),
  })
  await page.viewport(420, 900)
  await waitFor(() =>
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(422)
  )
  expect(
    screen.getByRole("button", { name: "Restore for comparison" })
  ).toBeVisible()
  await page.screenshot({
    path: "/private/tmp/loupe-duplicate-decision-narrow.png",
    element: screen.getByRole("main"),
  })
  fireEvent.change(
    screen.getByLabelText("Reason for restoring to review (optional)"),
    { target: { value: "Compare the extra source page." } }
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Restore for comparison" })
  )
  expect(
    await screen.findByRole("heading", { name: "Restored for review" })
  ).toBeVisible()
  expect(
    screen.getByText(/does not add transactions or mark it ready/)
  ).toBeVisible()
  expect(fetchAPI).toHaveBeenCalledTimes(1)
})
