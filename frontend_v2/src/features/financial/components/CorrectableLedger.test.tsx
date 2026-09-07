import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { CorrectableLedger } from "./CorrectableLedger"
vi.mock("./LedgerFilters", () => ({
  LedgerFilters: ({ onApply }: { onApply: (p: object) => void }) => (
    <button onClick={() => onApply({ accountId: "a" })}>
      Apply fixture filter
    </button>
  ),
}))
vi.mock("./LedgerPanel", () => ({
  LedgerPanel: ({ params }: { params: object }) => (
    <p data-testid="params">{JSON.stringify(params)}</p>
  ),
}))
vi.mock("./QuarantinePanel", () => ({
  QuarantinePanel: () => <p>Held out fixture</p>,
}))
vi.mock("./CorrectionForm", () => ({ CorrectionForm: () => null }))
vi.mock("./LedgerSourceDialog", () => ({ LedgerSourceDialog: () => null }))
it("resets applied account filters on a case change", () => {
  const { rerender } = render(
    <CorrectableLedger caseId="one" onAdjudicate={vi.fn()} />
  )
  fireEvent.click(screen.getByText("Apply fixture filter"))
  expect(screen.getByTestId("params")).toHaveTextContent('"accountId":"a"')
  rerender(<CorrectableLedger caseId="two" onAdjudicate={vi.fn()} />)
  expect(screen.getByTestId("params")).toHaveTextContent("{}")
})
it("does not attach current-ledger filters to held out rows", () => {
  render(<CorrectableLedger caseId="one" heldOut onAdjudicate={vi.fn()} />)
  expect(screen.queryByText("Apply fixture filter")).not.toBeInTheDocument()
  expect(screen.getByText("Held out fixture")).toBeInTheDocument()
})
