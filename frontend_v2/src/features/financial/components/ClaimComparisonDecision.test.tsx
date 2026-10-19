import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import fixture from "../lib/claim-comparison.fixture.json"
import {
  verifyClaimComparison,
  type VerifiedClaimComparison,
} from "../lib/claim-comparison"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { ClaimComparisonDecision } from "./ClaimComparisonDecision"

const save = vi.hoisted(() => ({
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  data: undefined,
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => save,
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
let report: VerifiedClaimComparison
beforeEach(async () => {
  useFinancialDraftStore.setState({ drafts: {} })
  save.mutate.mockReset()
  const captured = JSON.parse(fixture.scenario_json)
  report = await verifyClaimComparison(
    fixture,
    captured.case_id,
    captured.inputs
  )
})
function fill() {
  fireEvent.change(screen.getByLabelText("Claim proposal response"), {
    target: { value: "disagree" },
  })
  fireEvent.change(screen.getByLabelText("Claim review reason"), {
    target: { value: "The account holder still needs to be established." },
  })
  const select = screen.getByLabelText(
    "Supporting claim comparison readings"
  ) as HTMLSelectElement
  select.options[0].selected = true
  fireEvent.change(select)
}
const submit = () =>
  screen.getByRole("button", { name: "Save claim review with sources" })

it("restores the response, explanation and supporting payments after remount", () => {
  const first = render(<ClaimComparisonDecision report={report} />)
  fill()
  first.unmount()
  render(<ClaimComparisonDecision report={report} />)
  expect(screen.getByLabelText("Claim proposal response")).toHaveValue(
    "disagree"
  )
  expect(screen.getByLabelText("Claim review reason")).toHaveValue(
    "The account holder still needs to be established."
  )
  expect(
    screen.getByLabelText("Supporting claim comparison readings")
  ).toHaveValue([report.value.comparison.candidates[0].entry.transaction_id])
  expect(submit()).toBeEnabled()
})

it("requires the current calculation to be reviewed before saving a restored response", () => {
  const view = render(<ClaimComparisonDecision report={report} />)
  fill()
  const recalculated = {
    ...report,
    envelope: { ...report.envelope, scenario_sha256: "b".repeat(64) },
  }
  view.rerender(<ClaimComparisonDecision report={recalculated} />)
  expect(submit()).toBeDisabled()
  fireEvent.click(submit())
  expect(save.mutate).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Use recalculated comparison" })
  )
  fireEvent.click(submit())
  expect(save.mutate).toHaveBeenCalledTimes(1)
  expect(save.mutate.mock.calls[0][0].links[0].metadata.comparison_sha256).toBe(
    "b".repeat(64)
  )
})

it("requires unavailable supporting payments to be removed explicitly", () => {
  const view = render(<ClaimComparisonDecision report={report} />)
  fill()
  view.rerender(
    <ClaimComparisonDecision
      report={{
        ...report,
        value: {
          ...report.value,
          comparison: { ...report.value.comparison, candidates: [] },
        },
      }}
    />
  )
  expect(submit()).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Remove unavailable selections" })
  )
  expect(submit()).toBeEnabled()
  expect(screen.getByLabelText("Claim review reason")).toHaveValue(
    "The account holder still needs to be established."
  )
})

it("does not use a response written for another quotation", () => {
  const view = render(<ClaimComparisonDecision report={report} />)
  fill()
  view.rerender(
    <ClaimComparisonDecision
      report={{
        ...report,
        value: {
          ...report.value,
          inputs: { ...report.value.inputs, quote: "A different statement." },
        },
      }}
    />
  )
  expect(screen.getByLabelText("Claim review reason")).toHaveValue("")
  expect(submit()).toBeDisabled()
})

it("keeps the draft until the save succeeds", () => {
  const view = render(<ClaimComparisonDecision report={report} />)
  fill()
  fireEvent.click(submit())
  expect(Object.keys(useFinancialDraftStore.getState().drafts)).toHaveLength(1)
  act(() => save.mutate.mock.calls[0][1].onSuccess())
  view.unmount()
  render(<ClaimComparisonDecision report={report} />)
  expect(screen.getByLabelText("Claim review reason")).toHaveValue("")
})
