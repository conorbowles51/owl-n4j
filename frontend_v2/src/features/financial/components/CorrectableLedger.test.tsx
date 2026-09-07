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

vi.mock("./LedgerSummaryPanel", () => ({ LedgerSummaryPanel: () => null }))

vi.mock("./LedgerTrendsPanel", () => ({ LedgerTrendsPanel: () => null }))

vi.mock("./LedgerExportButton", () => ({
  LedgerExportButton: ({caseId,params}:{caseId:string;params:object}) => <p data-testid="export-scope">{caseId}:{JSON.stringify(params)}</p>,
}))
it("exports the applied primary ledger scope and removes export on held-out switch", () => {
  const {rerender}=render(<CorrectableLedger caseId="one" onAdjudicate={vi.fn()}/>)
  fireEvent.click(screen.getByText("Apply fixture filter"))
  expect(screen.getByTestId("export-scope")).toHaveTextContent('one:{"accountId":"a"}')
  rerender(<CorrectableLedger caseId="two" onAdjudicate={vi.fn()}/>)
  expect(screen.getByTestId("export-scope")).toHaveTextContent('two:{}')
  rerender(<CorrectableLedger caseId="two" heldOut onAdjudicate={vi.fn()}/>)
  expect(screen.queryByTestId("export-scope")).not.toBeInTheDocument()
})
