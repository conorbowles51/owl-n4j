import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { CorrectionHistory } from "./CorrectionHistory"

vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: (props: {
    caseId: string
    transactionId: string
    onClose: () => void
  }) => (
    <div role="dialog">
      {props.caseId}:{props.transactionId}
      <button onClick={props.onClose}>Close source</button>
    </div>
  ),
}))
const before = {
  row: {
    key: "old",
    ref_id: "TX-OLD",
    amount_minor: "9007199254740993",
    currency: "GBP",
    direction: "credit",
  },
}
const after = {
  row: {
    ...before.row,
    key: "new",
    ref_id: "TX-NEW",
    amount_minor: "9007199254740994",
  },
}
it("opens each historical version by its own ID without changing the recorded readings", () => {
  render(<CorrectionHistory before={before} after={after} caseId="case" />)
  fireEvent.click(screen.getByText("Original and replacement readings"))
  fireEvent.click(screen.getByRole("button", { name: "View original source" }))
  expect(screen.getByRole("dialog")).toHaveTextContent("case:old")
  fireEvent.click(screen.getByRole("button", { name: "Close source" }))
  fireEvent.click(
    screen.getByRole("button", { name: "View replacement source" })
  )
  expect(screen.getByRole("dialog")).toHaveTextContent("case:new")
  expect(screen.getByText(/Original TX-OLD/)).toHaveTextContent(
    "90071992547409.93 GBP"
  )
  expect(screen.getByText(/Replacement TX-NEW/)).toHaveTextContent(
    "90071992547409.94 GBP"
  )
})
it("does not carry an open source into another case", () => {
  const view = render(
    <CorrectionHistory before={before} after={after} caseId="first" />
  )
  fireEvent.click(screen.getByText("Original and replacement readings"))
  fireEvent.click(screen.getByRole("button", { name: "View original source" }))
  view.rerender(
    <CorrectionHistory before={before} after={after} caseId="second" />
  )
  expect(screen.queryByRole("dialog")).toBeNull()
})
it("offers no source navigation without case context or readable snapshots", () => {
  const view = render(<CorrectionHistory before={before} after={after} />)
  fireEvent.click(screen.getByText("Original and replacement readings"))
  expect(
    screen.queryByRole("button", { name: "View original source" })
  ).toBeNull()
  view.rerender(<CorrectionHistory before={{}} after={after} caseId="case" />)
  expect(screen.getByText(/history is unavailable/)).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "View replacement source" })
  ).toBeNull()
})
