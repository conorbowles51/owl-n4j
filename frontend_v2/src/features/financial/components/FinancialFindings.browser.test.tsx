import "@/styles/globals.css"
import "../financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react"
import { beforeEach, afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { MemoryRouter } from "react-router-dom"
import { FinancialFindings } from "./FinancialFindings"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./FinancialReportBuilder", () => ({
  FinancialReportBuilder: () => null,
}))
vi.mock("./FindingReportBundle", () => ({ FindingReportBundle: () => null }))
const saved = vi.hoisted(() => ({
  edit: null as { title: string; body: string; version: number } | null,
}))
vi.mock("@/features/workspace/casework-api", () => ({
  caseworkAPI: {
    update: async (
      caseId: string,
      _id: string,
      input: { title: string; body: string; expected_version: number }
    ) => {
      saved.edit = {
        title: input.title,
        body: input.body.trimEnd(),
        version: input.expected_version + 1,
      }
      return { case_id: caseId, ...saved.edit }
    },
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
        body: "## Evidence reviewed\nThe **two statements** record this movement. The supporting evidence still needs review.\n\n## Next action\nCompare the source invoices.\n\n## Assigned to",
        links: [],
        entry_type: "note",
        version: 1,
        author_name: "Example investigator",
        updated_at: "2026-09-24T01:00:00Z",
        ...(i === 0 && saved.edit ? saved.edit : {}),
      })),
    }),
  },
}))
beforeEach(() => {
  saved.edit = null
  useFinancialDraftStore.setState({ drafts: {} })
})
afterEach(cleanup)
function mount() {
  return render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <FinancialFindings caseId="synthetic-case" />
      </QueryClientProvider>
    </MemoryRouter>
  )
}
it("lets an investigator scan, expand, select and return to compact saved work", async () => {
  useFinancialDraftStore.setState({ drafts: {} })
  await page.viewport(1360, 900)
  const first = mount()
  const title = await screen.findByRole("button", {
    name: "Same-day transfer between company accounts",
  })
  expect(screen.queryByText("Compare the source invoices.")).toBeNull()
  expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(8)
  const cards = screen.getAllByRole("article")
  const firstBox = cards[0].getBoundingClientRect()
  const secondBox = cards[1].getBoundingClientRect()
  expect(firstBox.width).toBeLessThanOrEqual(352)
  expect(Math.abs(firstBox.width - firstBox.height)).toBeLessThan(2)
  expect(secondBox.top).toBe(firstBox.top)
  expect(secondBox.left).toBeGreaterThan(firstBox.right)
  const actionBox = within(cards[0])
    .getByRole("button", { name: "Add to Timeline" })
    .getBoundingClientRect()
  expect(actionBox.top - title.getBoundingClientRect().bottom).toBeLessThan(25)
  expect(actionBox.right).toBeLessThanOrEqual(firstBox.right)
  await page
    .getByRole("region", { name: "Financial findings and notes" })
    .screenshot({ path: "/private/tmp/loupe-compact-findings.png" })
  fireEvent.click(
    screen.getByLabelText(
      "Include Same-day transfer between company accounts in report"
    )
  )
  await page
    .getByRole("button", {
      name: "Same-day transfer between company accounts",
      exact: true,
    })
    .click()
  expect(screen.getByText("Compare the source invoices.")).toBeVisible()
  expect(
    screen.getByRole("heading", { name: "Evidence reviewed" })
  ).toBeVisible()
  expect(cards[0].textContent).not.toContain("##")
  expect(cards[0].textContent).not.toContain("Assigned to")
  await page
    .getByRole("article", {
      name: "Same-day transfer between company accounts",
    })
    .screenshot({ path: "/private/tmp/loupe-findings-expanded.png" })
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

it("opens Edit from a collapsed card and saves a trimmed legacy note without storage headings", async () => {
  await page.viewport(1360, 900)
  const first = mount()
  const title = "Same-day transfer between company accounts"
  await screen.findByRole("button", { name: title })
  await page
    .getByRole("article", { name: title })
    .getByRole("button", { name: "Edit", exact: true })
    .click()
  const editor = await screen.findByRole("dialog", { name: "Edit finding" })
  expect(within(editor).getByLabelText("Explanation")).not.toHaveValue(
    expect.stringContaining("## Assigned to")
  )
  await page
    .getByRole("textbox", { name: "Title", exact: true })
    .fill("Reviewed account movement")
  await page.getByRole("button", { name: "Save finding", exact: true }).click()
  await screen.findByText(
    "Saved to this case. Colleagues with access can open it in Findings & Observations."
  )
  await page
    .getByRole("button", { name: "Return to investigation", exact: true })
    .click()
  expect(saved.edit?.version).toBe(2)
  first.unmount()
  mount()
  await screen.findByRole("button", { name: "Reviewed account movement" })
  await page
    .getByRole("button", { name: "Reviewed account movement", exact: true })
    .click()
  const reopened = screen.getByRole("article", {
    name: "Reviewed account movement",
  })
  expect(
    within(reopened).getByRole("heading", { name: "Evidence reviewed" })
  ).toBeVisible()
  expect(reopened.textContent).not.toContain("##")
  expect(reopened.textContent).not.toContain("Assigned to")
})
