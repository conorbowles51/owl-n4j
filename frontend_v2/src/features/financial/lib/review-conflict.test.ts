import { describe, expect, it } from "vitest"
import { ApiError } from "@/lib/api-client"
import { isReviewConflict, reviewDifferences } from "./review-conflict"

describe("review conflict", () => {
  it("recognises only a refusal because someone saved first", () => {
    expect(isReviewConflict(new ApiError("Another reviewer saved this statement.", 409))).toBe(true)
    expect(isReviewConflict(new ApiError("Another user saved changes to this review.", 409))).toBe(true)
    expect(isReviewConflict(new ApiError("The statement reading changed.", 409))).toBe(false)
    expect(isReviewConflict(new ApiError("Another reviewer saved this statement.", 500))).toBe(false)
    expect(isReviewConflict(Error("Another reviewer saved"))).toBe(false)
  })

  it("lists statement fields and payment fields that differ, and nothing else", () => {
    const saved = {
      holder: "Saved holder",
      period_end: "",
      rows: [
        { id: "a", description: "Rent", amount_minor: "100", excluded: false },
        { id: "b", description: "Saved only", amount_minor: "5" },
      ],
    }
    const local = {
      holder: "My holder",
      period_end: null,
      rows: [
        { id: "a", description: "Rent", amount_minor: "120", excluded: true },
        { id: "c", description: "Mine only", amount_minor: "7" },
      ],
    }
    expect(reviewDifferences(saved, local)).toEqual([
      { key: "holder", label: "Account holder", saved: "Saved holder", local: "My holder" },
      { key: "a:amount_minor", label: "Payment Rent: amount", saved: "100", local: "120" },
      { key: "a:excluded", label: "Payment Rent: excluded", saved: "No", local: "Yes" },
      { key: "b:presence", label: "Payment Saved only", saved: "Present", local: "Not in this version" },
      { key: "c:presence", label: "Payment Mine only", saved: "Not in this version", local: "Present" },
    ])
  })
})
