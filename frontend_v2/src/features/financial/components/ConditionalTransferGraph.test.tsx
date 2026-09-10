import { render, screen, fireEvent } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { ConditionalTransferGraph } from "./ConditionalTransferGraph"
import { transferInputs } from "../lib/ledger-transfers"
const scope = transferInputs.parse({
  case_id: "case",
  start_date: null,
  end_date: null,
  population: "working",
  tolerance_days: 3,
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Synthetic",
  excluded_rows: 0,
  date_unavailable_ids: [],
  candidates: [],
  rows: [
    ...[
      ["d", "a", "debit"],
      ["c", "b", "credit"],
      ["d2", "b", "debit"],
      ["c2", "c", "credit"],
    ].map(([key, account_id, direction]) => ({
      key,
      account_id,
      direction,
      case_id: "case",
      account_label: account_id,
      source_document_id: "source",
      currency: "GBP",
      amount_minor: "9007199254740993",
      ordering_date: "2026-01-01",
      description: "Synthetic",
    })),
  ],
})
const pairs = [
  { debit_id: "d", credit_id: "c" },
  { debit_id: "d2", credit_id: "c2" },
]
vi.mock("./LedgerGraphCanvas", () => ({
  default: () => <div>Graph canvas</div>,
}))
it("filters account connections and opens both sides without changing pairings", async () => {
  const source = vi.fn()
  render(
    <ConditionalTransferGraph scope={scope} pairs={pairs} onSource={source} />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Show transfer relationship graph" })
  )
  await screen.findByText("Graph canvas")
  fireEvent.change(screen.getByLabelText("Inspect connected account"), {
    target: { value: "a" },
  })
  expect(
    screen.getByText("1 paired movements match this graph selection.")
  ).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect paired outgoing d" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect paired incoming c" })
  )
  expect(source.mock.calls).toEqual([["d"], ["c"]])
  fireEvent.click(
    screen.getByRole("button", { name: "Show all paired movements" })
  )
  expect(
    screen.getByText("2 paired movements match this graph selection.")
  ).toBeInTheDocument()
})
