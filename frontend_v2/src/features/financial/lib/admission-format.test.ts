import { describe, expect, it } from "vitest"
import { ApiError } from "@/lib/api-client"
import { readAdmissionRefusal, readFileAdmission } from "./admission-format"

const admission = {
  file_id: "a",
  outcome: "admitted",
  admitted: true,
  routed_to: "document_pipeline",
  reason: "Reviewed",
  route_outcome: "ambiguous",
  detected_format: null,
  claimants: ["bai2", "mt940"],
  adjudication_id: "decision-1",
}
const held = {
  file_id: "a",
  file_name: "a.dat",
  route_outcome: "ambiguous",
  detected_format: null,
  claimants: ["bai2", "mt940"],
}
const refusal = (files: unknown[]) =>
  new ApiError("Held", 409, {
    detail: { error: "unadmitted_files", message: "Held", held: files },
  })

describe("reading admission answers", () => {
  it("distinguishes a recorded decision from processing", () => {
    expect(readFileAdmission(admission, "a")).toMatchObject({
      canProcess: true,
      decisionRecorded: true,
      reasonLabel: "Your recorded reason",
    })
    expect(readFileAdmission(admission, "a").message).toContain(
      "has not been sent"
    )
  })
  it("allows an explicit send when a fresh check finds no hold without claiming a decision", () => {
    expect(
      readFileAdmission(
        {
          ...admission,
          outcome: "nothing_to_override",
          admitted: false,
          adjudication_id: null,
          routed_to: "held",
        },
        "a"
      )
    ).toMatchObject({
      canProcess: true,
      decisionRecorded: false,
      reasonLabel: "System response",
    })
  })
  it("reports a 200 refusal as a refusal, with the system's reason", () => {
    expect(
      readFileAdmission(
        {
          ...admission,
          outcome: "refused",
          admitted: false,
          adjudication_id: null,
        },
        "a"
      )
    ).toMatchObject({
      canProcess: false,
      reasonLabel: "System response",
      reason: "Reviewed",
    })
  })
  it.each([
    { outcome: "future_outcome" },
    { admitted: false },
    { adjudication_id: null },
    { routed_to: "held" },
    { file_id: "other" },
    { claimants: [4] },
  ])("never enables processing for an inconsistent answer: %j", (change) => {
    expect(readFileAdmission({ ...admission, ...change }, "a").canProcess).toBe(
      false
    )
  })
  it.each([null, [], {}, "admitted"])(
    "handles malformed answers: %j",
    (value) => {
      expect(readFileAdmission(value, "a").canProcess).toBe(false)
    }
  )
  it("retains evidence of a possible write for cache invalidation", () => {
    expect(
      readFileAdmission({ ...admission, outcome: "future" }, "a")
        .decisionRecorded
    ).toBe(true)
  })
})

describe("reading a processing refusal", () => {
  it("keeps all files and the finding actually returned by the refusing request", () => {
    expect(
      readAdmissionRefusal(
        refusal([held, { ...held, file_id: "b", route_outcome: "future" }])
      )?.held
    ).toEqual([held, { ...held, file_id: "b", route_outcome: "future" }])
  })
  it.each(
    [[], [held, {}], [held, held], [{ ...held, claimants: null }]].map(
      (files) => ({ files })
    )
  )("rejects an incomplete envelope: %j", ({ files }) => {
    expect(readAdmissionRefusal(refusal(files))).toBeNull()
  })
  it("does not interpret an unrelated error as an admission opportunity", () => {
    expect(
      readAdmissionRefusal(
        new ApiError("conflict", 409, {
          detail: { error: "other", held: [held] },
        })
      )
    ).toBeNull()
    expect(
      readAdmissionRefusal(new ApiError("forbidden", 403, refusal([held]).data))
    ).toBeNull()
  })
})
