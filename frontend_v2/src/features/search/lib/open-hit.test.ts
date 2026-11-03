import { describe, expect, it } from "vitest"
import { hitPath } from "./open-hit"

describe("hitPath", () => {
  it("opens machine-generated text beside its file on the Media screen (M-3)", () => {
    const hit = { kind: "machine_text", title: "C1 text read from synthetic-a.jpg", snippet: null, record_uid: null, evidence_file_id: null,
      open: { screen: "media", params: { file_uid: "f1", extraction_id: "e1" } } }
    expect(hitPath("c", hit)).toBe("/cases/c/phones/e1/records/media?file=f1")
  })
})
