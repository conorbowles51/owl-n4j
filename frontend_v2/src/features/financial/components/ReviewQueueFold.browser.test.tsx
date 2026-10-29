import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialStore } from "../stores/financial.store"
import { FinancialPage } from "./FinancialPage"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()), fetchAPI: vi.fn(),
}))
vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: { id: "case", title: "Synthetic fold measurement" }, isPending: false }),
}))
vi.mock("../hooks/use-financial-access", async (original) => ({
  ...(await original<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))

// Seven statements waiting, none done: the shape of the queue Alex tested on.
const entry = (n: number) => ({
  id: `i${n}`, batch_id: "b1", file_id: `f${n}`, file_ids: [`f${n}`], source_id: `f${n}`, statement_id: `s${n}`,
  filename: `CommitmentLetter (${n}).pdf`, holder: "Holder", account: `000${n}`, institution: "Bank", currency: "USD",
  period_start: "", period_end: "", page: 1, can_import: false, status: "attention",
  bucket: "waiting", file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1,
  issue: "Opening balance is not printed", issue_reason: "balance", reasons: ["balance"],
})
const counts = { imported: 0, saving: 0, waiting: 7, ready: 0, filled: 0, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }
const queue = { case_id: "case", file_ids: [], counts, status_line: "", items: [1, 2, 3, 4, 5, 6, 7].map(entry),
  ready: [], copies: [], unreadable: [], unreadable_files: [], rechecking: [] }

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ user: { id: "u1", username: "alex", name: "Alexandra Test", role: null } })
  useFinancialStore.getState().reset()
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return queue as never
    if (url.startsWith("/api/evidence?")) return { files: [] } as never
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (url.includes("/statement-import/files?")) return { case_id: "case", files: [], truncated: false } as never
    if (url.includes("/deployment-recovery?")) return { run: null, total: 0, counts: {}, items: [] } as never
    if (url.includes("/ledger-categories?")) return { case_id: "case", categories: [] } as never
    if (url.startsWith("/api/financial?")) return { transactions: [], total: 0, dataset_mode: "transactions", uses_legacy_financial_model: false } as never
    if (url.includes("/categories?")) return { categories: [] } as never
    if (url.includes("/entities?")) return { entities: [] } as never
    return { case_id: "case", applied: false, offset: 0, has_more: false, items: [], accounts: [], transactions: [], total: 0, runs: [], decisions: [], files: [], entries: [] } as never
  })
})
afterEach(() => cleanup())

// The app shell beside the page: the expanded sidebar (w-56) and a page as tall as the window.
function mount(height: number) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1"]}>
          <Routes>
            <Route
              path="/cases/:id/financial"
              element={
                <div className="flex" style={{ height }}>
                  <div className="w-56 shrink-0" />
                  <main className="flex min-w-0 flex-1 flex-col overflow-hidden"><FinancialPage /></main>
                </div>
              }
            />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

for (const [width, height] of [[1280, 720], [1440, 900]] as const) {
  it(`shows the first statement to review without scrolling at ${width}x${height}`, async () => {
    await page.viewport(width, height)
    mount(height)
    const list = await screen.findByRole("list", { name: "Statements to review" })
    const glance = screen.getByRole("region", { name: "Statements at a glance" })
    const first = within(list).getAllByRole("listitem")[0]
    const card = glance.getBoundingClientRect()
    const item = first.getBoundingClientRect()
    console.info(`fold ${width}x${height}: glance height ${Math.round(card.height)}, first item top ${Math.round(item.top)}, bottom ${Math.round(item.bottom)}`)
    // The headline, what needs a person and every count are one line; every legend meaning stays named.
    expect(glance).toHaveTextContent("0 of 7 statements are done. 7 need your eyes.")
    expect(within(glance).getByRole("button", { name: /7 need you/ })).toBeVisible()
    expect(card.height).toBeLessThan(70)
    // The first item is on screen (it started at 741 and 697 before; the card was 209 tall): what is
    // wrong, what to do, and its actions (Preview, Open page 1). Its fields follow below at 1280x720.
    for (const part of [
      within(first).getByLabelText("What is wrong"),
      within(first).getByRole("list", { name: "What to do" }),
      within(first).getByRole("button", { name: "Preview" }),
      within(first).getByRole("button", { name: "Open page 1" }),
    ])
      expect(part.getBoundingClientRect().bottom, part.textContent ?? "").toBeLessThanOrEqual(height)
    if (height >= 900) expect(item.bottom).toBeLessThanOrEqual(height)
    // No band of its own for "Reset view": it sits in the tab bar.
    const reset = screen.getByRole("button", { name: "Reset view" })
    expect(reset.parentElement?.parentElement).toContainElement(screen.getByRole("tablist", { name: "Financial" }))
  })
}

// Every Financial tab starts its content right under the tab bar: no band holding only "Reset view".
it("leaves no empty band under the tab bar on any Financial tab", async () => {
  await page.viewport(1440, 900)
  mount(900)
  await screen.findByRole("list", { name: "Statements to review" })
  const bar = screen.getByRole("tablist", { name: "Financial" }).parentElement!
  const tools = ["Compare transfers", "Look for patterns", "Payment graph", "Trace funds", "Payments and case events",
    "Import review", "Excluded transactions", "Processing history", "Change history"]
  const tabs = ["Overview", "Statements & accounts", "Transactions", "People & businesses", "Follow money", "Trends",
    "Findings & Observations", ...tools]
  const gaps: string[] = []
  for (const name of tabs) {
    if (tools.includes(name)) {
      await page.getByRole("button", { name: /More financial tools/ }).click()
      await page.getByRole("menuitem", { name }).click()
    } else {
      await page.getByRole("tab", { name, exact: true }).click()
    }
    const panel = await vi.waitFor(() => {
      const open = document.querySelector('[role="tabpanel"]:not([style*="display: none"])[data-state="active"]')
      if (!open) throw Error(`no open panel for ${name}`)
      return open
    })
    await new Promise((resolve) => setTimeout(resolve, 150))
    // The first painted thing in the open tab: text, an icon, or a card's border or background.
    const panelBox = panel.getBoundingClientRect()
    let top = Infinity
    for (const el of Array.from(panel.querySelectorAll("*"))) {
      const box = el.getBoundingClientRect()
      if (!box.height || !box.width) continue
      const style = getComputedStyle(el)
      const text = Array.from(el.childNodes).some((child) => child.nodeType === Node.TEXT_NODE && child.textContent?.trim())
      const painted = text || el.tagName.toLowerCase() === "svg" || parseFloat(style.borderTopWidth) > 0 ||
        style.backgroundImage !== "none" ||
        (style.backgroundColor !== "rgba(0, 0, 0, 0)" && box.height < panelBox.height * 0.9)
      if (painted) top = Math.min(top, box.top)
    }
    const gap = Math.round(top - bar.getBoundingClientRect().bottom)
    // A tab with nothing in it centres its "nothing here" message on purpose.
    const emptyState = !!panel.querySelector(".py-12.text-center")
    gaps.push(`${name}: ${gap}${emptyState ? " (centred empty-state message)" : ""}`)
    if (!emptyState) expect(gap, name).toBeLessThan(48)
    expect(screen.getAllByRole("button", { name: "Reset view" })).toHaveLength(1)
    expect(bar).toContainElement(screen.getByRole("button", { name: "Reset view" }))
  }
  console.info(`first content under the tab bar: ${gaps.join(", ")}`)
}, 60_000)

// The quick preview at 1280 wide: page and fields side by side, inside the window, keys move it.
it("fits the quick preview, its page and its fields in a 1280x720 window", async () => {
  await page.viewport(1280, 720)
  mount(720)
  const list = await screen.findByRole("list", { name: "Statements to review" })
  within(list).getAllByRole("button", { name: "Preview" })[0].click()
  const panel = await screen.findByRole("dialog", { name: "Preview of CommitmentLetter (1).pdf" })
  const box = panel.getBoundingClientRect()
  const pageBox = within(panel).getByRole("region", { name: /^Page 1 of/ }).getBoundingClientRect()
  const fields = within(panel).getByRole("region", { name: "What it needs" }).getBoundingClientRect()
  console.info(`preview 1280x720: panel ${Math.round(box.left)}-${Math.round(box.right)}, page ${Math.round(pageBox.width)} wide, fields ${Math.round(fields.left)}-${Math.round(fields.right)} top ${Math.round(fields.top)}`)
  expect(box.left).toBeGreaterThanOrEqual(0)
  expect(box.right).toBeLessThanOrEqual(1280)
  // Side by side: the page beside the fields, both starting at the top of the panel.
  expect(fields.left).toBeGreaterThanOrEqual(pageBox.right - 1)
  expect(fields.right).toBeLessThanOrEqual(1280)
  expect(pageBox.width).toBeGreaterThan(500)
  expect(within(panel).getByLabelText("Before it can be imported")).toBeVisible()
  await userKey("j")
  expect(await screen.findByRole("dialog", { name: "Preview of CommitmentLetter (2).pdf" })).toBeVisible()
  await userKey("Escape")
  await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
})

async function userKey(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }))
  await new Promise((resolve) => setTimeout(resolve, 50))
}
