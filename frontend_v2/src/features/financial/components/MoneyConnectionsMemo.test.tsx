import { render, screen, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { MoneyConnections } from "./InvestigatorFollowMoney"
import * as workspace from "../lib/investigator-workspace"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import type { LedgerTransaction } from "../api"

vi.mock("../lib/investigator-workspace", async (original) => {
  const actual = await original<typeof import("../lib/investigator-workspace")>()
  return { ...actual, paymentProfiles: vi.fn(actual.paymentProfiles) }
})
afterEach(cleanup)

// Grouping every payment into profiles took about 0.7 s per render on d5b330d1's 27,926 payments; the Overview
// renders once per request that lands, so the grouping must run once per row list, not once per render.
it("groups the payments once per row list, however often the page renders", () => {
  const rows: LedgerTransaction[] = [
    { ...paymentFixture, key: "a", direction: "debit", from_name: "Owner", to_name: "Shop", currency: "USD", amount_minor: "100" },
    { ...paymentFixture, key: "b", direction: "credit", from_name: "Payer", to_name: "Owner", currency: "USD", amount_minor: "250" },
  ]
  const profiles = vi.mocked(workspace.paymentProfiles)
  const view = render(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  const first = profiles.mock.calls.length
  expect(first).toBeGreaterThan(0)
  const shown = view.container.textContent
  for (let i = 0; i < 3; i++) view.rerender(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  expect(profiles.mock.calls.length).toBe(first)
  expect(view.container.textContent).toBe(shown)
  // A new row list is grouped again.
  view.rerender(<MoneyConnections rows={[...rows]} onOpen={vi.fn()} />)
  expect(profiles.mock.calls.length).toBe(first * 2)
  expect(screen.getAllByRole("button", { name: /Payer|Shop/ }).length).toBeGreaterThan(0)
})
