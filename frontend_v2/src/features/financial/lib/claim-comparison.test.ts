import { expect, it } from "vitest"
import fixture from "./claim-comparison.fixture.json"
import { verifyClaimComparison } from "./claim-comparison"
import { claimReviewNote } from "./claim-review-note"
const captured = JSON.parse(fixture.scenario_json),
  request = captured.inputs,
  caseId = captured.case_id
it("verifies backend-generated comparison bytes and refuses input or digest changes", async () => {
  expect(
    (await verifyClaimComparison(fixture, caseId, request)).value
      .claim_proof_class
  ).toBe("p4")
  await expect(
    verifyClaimComparison(fixture, caseId, {
      ...request,
      quote: "Changed quote",
    })
  ).rejects.toThrow("differs")
  await expect(
    verifyClaimComparison(
      { ...fixture, scenario_sha256: "0".repeat(64) },
      caseId,
      request
    )
  ).rejects.toThrow("integrity")
})
it("preserves a reviewer response and selected source reading in one grouped evidence attachment", async () => {
  const verified = await verifyClaimComparison(fixture, caseId, request),
    id = verified.value.comparison.candidates[0].entry.transaction_id,
    note = claimReviewNote(
      verified,
      "disagree",
      "The holder was an unverified assumption.",
      [id]
    )
  expect(note.entry_type).toBe("note")
  expect(note.body).toContain("disagrees")
  expect(note.body).toContain(request.quote)
  expect(note.links).toHaveLength(1)
  expect(note.links?.[0].source_anchor).toMatchObject({
    quote: request.quote,
    financial_transaction_ids: [id],
  })
  expect(note.links?.[0].metadata).toMatchObject({
    claim_proof_class: "p4",
    decision: "disagree",
    comparison_sha256: fixture.scenario_sha256,
  })
  expect(() => claimReviewNote(verified, "agree", "", [])).toThrow("Explain")
  expect(() => claimReviewNote(verified, "agree", "Reason", ["other"])).toThrow(
    "distinct"
  )
})
