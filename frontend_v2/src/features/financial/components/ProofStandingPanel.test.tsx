import { fireEvent, render, screen, within } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { proofStanding } from "@/test/proof-standing-fixture"
import { ProofStandingPanel } from "./ProofStandingPanel"

const hook = vi.hoisted(() => vi.fn())
vi.mock("../hooks/use-proof-standing", () => ({ useProofStanding: hook }))
const refetch = vi.fn()
beforeEach(() => {
  refetch.mockReset()
  hook.mockReturnValue({
    data: proofStanding(),
    isPending: false,
    isError: false,
    isFetching: false,
    refetch,
  })
})
const expand = () =>
  fireEvent.click(screen.getByText("View all classes and their rules"))

it("states scope without calling the class counts outstanding reviews", () => {
  render(<ProofStandingPanel caseId="case-1" />)
  expect(screen.getByTestId("proof-standing-totals")).toHaveTextContent(
    "5 financial source documents · 9 ledger rows"
  )
  expect(screen.getByTestId("proof-standing-human-decision")).toHaveTextContent(
    "2 documents and 4 rows"
  )
  expect(
    screen.getByText(/These counts include held-out, superseded and rejected/)
  ).toBeInTheDocument()
  expect(
    screen.getByText(/not reviews still waiting for a decision/)
  ).toBeInTheDocument()
})
it("shows every class including zeroes, with all four server rules", () => {
  render(<ProofStandingPanel caseId="case-1" />)
  expand()
  const rows = screen.getAllByRole("row")
  expect(rows).toHaveLength(6)
  expect(
    within(rows[1])
      .getAllByRole("cell")
      .map((cell) => cell.textContent)
  ).toEqual(["0", "0", "Yes", "No", "Yes", "Yes"])
  expect(
    within(rows[4])
      .getAllByRole("cell")
      .map((cell) => cell.textContent)
  ).toEqual(["2", "4", "No", "Yes", "Yes", "No"])
  expect(
    screen.getByText(/Classes eligible for totals: P0, P1, P2/)
  ).toBeInTheDocument()
})
it("renders a future class explicitly and uses the supplied permissions", () => {
  const data = proofStanding()
  data.classes.push({ ...data.classes[3], proof_class: "p5" })
  hook.mockReturnValue({ data, refetch })
  render(<ProofStandingPanel caseId="case-1" />)
  expand()
  expect(screen.getByText("Unrecognised (p5)")).toBeInTheDocument()
  const row = screen.getAllByRole("row").at(-1)!
  expect(
    within(row)
      .getAllByRole("cell")
      .map((cell) => cell.textContent)
  ).toEqual(["2", "4", "No", "Yes", "Yes", "No"])
})
it("does not infer that an empty census means there is no financial evidence", () => {
  const data = proofStanding()
  data.classes.forEach((row) => {
    row.documents = 0
    row.transactions = 0
  })
  data.documents =
    data.transactions =
    data.documents_requiring_adjudication =
    data.transactions_requiring_adjudication =
      0
  hook.mockReturnValue({ data, refetch })
  render(<ProofStandingPanel caseId="case-1" />)
  expand()
  expect(
    screen.getByText(/does not mean the case has no financial evidence/)
  ).toBeInTheDocument()
  expect(screen.getAllByRole("row")).toHaveLength(6)
})
it("shows no counts without a case, even if a cached response exists", () => {
  render(<ProofStandingPanel caseId={undefined} />)
  expect(screen.queryByTestId("proof-standing-totals")).toBeNull()
  expect(screen.getByText(/Choose a case/)).toBeInTheDocument()
})
it("shows a loading state rather than a zero census", () => {
  hook.mockReturnValue({ isPending: true, isFetching: true, refetch })
  render(<ProofStandingPanel caseId="case-1" />)
  expect(screen.getByRole("status")).toHaveTextContent(
    "Reading evidence classification"
  )
  expect(screen.queryByTestId("proof-standing-totals")).toBeNull()
})
it("hides stale counts on a failed refresh and offers an explicit retry", () => {
  hook.mockReturnValue({
    data: proofStanding(),
    isError: true,
    error: new Error("Unavailable"),
    refetch,
  })
  render(<ProofStandingPanel caseId="case-1" />)
  expect(screen.getByRole("alert")).toHaveTextContent("No counts are shown")
  expect(screen.queryByTestId("proof-standing-totals")).toBeNull()
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh classification" })
  )
  expect(refetch).toHaveBeenCalledTimes(1)
})
it("labels the previous reading while a refresh is pending", () => {
  hook.mockReturnValue({ data: proofStanding(), isFetching: true, refetch })
  render(<ProofStandingPanel caseId="case-1" />)
  expect(screen.getByRole("status")).toHaveTextContent(
    "showing the last successful reading"
  )
  expect(
    screen.getByRole("button", { name: "Refresh classification" })
  ).toBeDisabled()
})
