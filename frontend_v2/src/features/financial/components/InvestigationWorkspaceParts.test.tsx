import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { PaymentSet } from "./InvestigationWorkspaceParts"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"

vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: () => false }))
vi.mock("./PaymentComparison", () => ({
  PaymentComparison: ({ ids }: { ids: string[] }) => (
    <output data-testid="compared">{ids.join(",")}</output>
  ),
}))
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
})

it("compares only explicit selections and retains payments hidden by a narrower view", () => {
  const rows = Array.from({ length: 26 }, (_, index) => ({
    ...paymentFixture,
    key: `payment-${index}`,
    description: `Payment ${index}`,
  }))
  const view = render(
    <PaymentSet caseId="case" rows={rows} title="Supporting payments" />
  )
  expect(
    screen.queryByRole("button", { name: /Compare \d+ payments/ })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("checkbox", { name: /Select Payment 0 on/ }))
  fireEvent.click(screen.getByRole("button", { name: "Next payments" }))
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Select Payment 25 on/ })
  )
  view.rerender(
    <PaymentSet caseId="case" rows={[rows[0]]} title="Supporting payments" />
  )
  expect(
    screen.getByText(/1 selected payments are outside this view/)
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: /Compare \d+ payments/ }))
  expect(screen.getByTestId("compared")).toHaveTextContent(
    "payment-0,payment-25"
  )
})
