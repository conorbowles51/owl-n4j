import "@/styles/globals.css"
import "../financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { FinancialFindings } from "./FinancialFindings"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./FinancialReportBuilder", () => ({
  FinancialReportBuilder: () => null,
}))
vi.mock("./FindingReportBundle", () => ({ FindingReportBundle: () => null }))
vi.mock("@/features/workspace/casework-api", () => ({
  caseworkAPI: {
    list: async () => ({
      total: 8,
      entries: Array.from({ length: 8 }, (_, i) => ({
        id: `finding-${i}`,
        case_id: "synthetic-case",
        title: [
          "Same-day transfer between company accounts",
          "Unexplained supplier payments",
          "Possible duplicate invoice",
          "Account ownership confirmed",
          "Payments requiring source documents",
          "Statement coverage gap",
          "Unidentified incoming transfer",
          "Investigation summary",
        ][i],
        tags: [
          "financial",
          "financial-workspace",
          i % 2 ? "financial-question" : "financial-observation",
          "financial-open",
        ],
        body: "The two statements record this movement. The supporting evidence still needs review.\n\n## Next action\nCompare the source invoices.\n\n## Assigned to\nInvestigator",
        links: [],
        entry_type: "note",
        version: 1,
        author_name: "Example investigator",
        updated_at: "2026-09-24T01:00:00Z",
      })),
    }),
  },
}))
it("lets an investigator scan, expand, select and return to compact saved work", async () => {
  useFinancialDraftStore.setState({ drafts: {} })
  await page.viewport(1360, 900)
  const mount = () =>
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <FinancialFindings caseId="synthetic-case" />
      </QueryClientProvider>
    )
  const first = mount()
  const title = await screen.findByRole("button", {
    name: "Same-day transfer between company accounts",
  })
  expect(screen.queryByText("Compare the source invoices.")).toBeNull()
  expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(8)
  await page
    .getByRole("region", { name: "Financial findings and notes" })
    .screenshot({ path: "/private/tmp/loupe-compact-findings.png" })
  fireEvent.click(
    screen.getByLabelText(
      "Include Same-day transfer between company accounts in report"
    )
  )
  fireEvent.click(title)
  expect(screen.getByText("Compare the source invoices.")).toBeVisible()
  first.unmount()
  mount()
  expect(
    await screen.findByRole("button", {
      name: "Same-day transfer between company accounts",
    })
  ).toHaveAttribute("aria-expanded", "true")
  expect(
    screen.getByLabelText(
      "Include Same-day transfer between company accounts in report"
    )
  ).toBeChecked()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Same-day transfer between company accounts",
    })
  )
  await page.viewport(420, 900)
  await page
    .getByRole("article", {
      name: "Same-day transfer between company accounts",
    })
    .screenshot({ path: "/private/tmp/loupe-compact-findings-narrow.png" })
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(420)
  cleanup()
})
