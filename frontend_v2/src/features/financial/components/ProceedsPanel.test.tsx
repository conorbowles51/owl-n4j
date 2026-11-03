vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: false, ready: true, error: false }),
}))
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ProceedsPanel } from "./ProceedsPanel"

const set = (key: string, label: string, low: string, high: string) => ({
  key, label, unit: "", kind: key === "price_per_deal" ? "money" : key === "share_deals" ? "percent" : "count",
  current: { id: `j-${key}` }, set_by: "Verification user", low, high, source: "doc://f/3", proposed: [], history: [],
})

it("labels the range an estimate, not measured, names who set each value and shows the move per assumption", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url: string) =>
    url.includes("/list")
      ? { items: [{ id: "p-1", title: "Line A", currency: "MXN", created_by: "Verification user" }], total: 1 }
      : {
          id: "p-1", case_id: "case-a", title: "Line A", currency: "MXN", period_start: null, period_end: null,
          created_by: "Verification user", label: "estimate, not measured",
          formula: "messages × share that are deals × deals per message × price per deal",
          assumptions: [set("messages", "Messages", "100", "200"), set("share_deals", "Share", "10", "20"),
            set("deals_per_message", "Deals per message", "1", "1"), set("price_per_deal", "Price per deal", "30000", "50000")],
          result: { low_minor: 300000, mid_minor: 787500, high_minor: 2000000, moves: [
            { key: "price_per_deal", label: "Price per deal", at_low_minor: 675000, at_high_minor: 1125000, swing_minor: 450000 }] },
          missing: [],
          deposits: { categories: [], verified_minor: 0, verified_rows: 0, left_out_rows: 0, left_out_classes: {}, note: "No deposit category chosen." },
        }
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProceedsPanel caseId="case-a" />
    </QueryClientProvider>
  )
  expect(await screen.findByText("estimate, not measured")).toBeVisible()
  expect(screen.getByText(/MX\$3,000.00/)).toBeVisible()
  expect(screen.getByText(/MX\$20,000.00/)).toBeVisible()
  expect(screen.getAllByText(/Set by Verification user · source: doc:\/\/f\/3/)).toHaveLength(4)
  expect(screen.getByRole("table", { name: "How the result moves per assumption" })).toHaveTextContent("MX$4,500.00")
  // A price is stored in minor units and shown in the currency (old code showed "30000 to 50000").
  expect(screen.getByText("MX$300.00 to MX$500.00")).toBeVisible()
})
