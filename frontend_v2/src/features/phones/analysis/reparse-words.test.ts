import { describe, expect, it } from "vitest"
import { reparseWords } from "./reparse-words"
import type { ApproachResult } from "./analysis-api"

/** 05 section 17.3: every disagreement names the tool and version, and both instants with their original strings. */
const r = (kind: string, measures: Record<string, unknown>) => ({ kind, measures, strength: "observation" }) as unknown as ApproachResult
const base = { read_by: "read by ALEAPP v2026.4.5", compared: "sms" }

describe("re-parse wording", () => {
  it("states both instants, both original strings and the difference in hours", () => {
    const w = reparseWords(r("time_differs", { ...base, difference_hours: 5,
      report: { instant: "2023-03-14T20:00:00+00:00", original: "3/14/2023 3:00:00 PM(UTC-5)" },
      reparse: { instant: "2023-03-15T01:00:00+00:00", original: "1678842000", artefact: "get_sms_mms", row_index: 2 } }))
    expect(w.title).toBe("A text message at different times: 5 hours apart")
    expect(w.line).toBe("In the report: 2023-03-14T20:00:00+00:00 (as written: 3/14/2023 3:00:00 PM(UTC-5)). Read by ALEAPP v2026.4.5 (get_sms_mms, row 2): 2023-03-15T01:00:00+00:00 (as written: 1678842000).")
  })
  it("labels a record only the tool read as the tool's, with where it came from", () => {
    const w = reparseWords(r("only_in_reparse", { ...base, reparse: { instant: null, shown: { party: "+12025550143", body: "synthetic" }, artefact: "get_sms_mms", row_index: 4 } }))
    expect(w.title).toBe("A text message read by ALEAPP v2026.4.5 (get_sms_mms, row 4), not in the report")
    expect(w.line).toContain("party: +12025550143; body: synthetic. Time no time.")
  })
  it("gives both totals when they differ", () => {
    expect(reparseWords(r("count_differs", { ...base, compared: "call", report_count: 1200, reparse_count: 1188 })).title)
      .toBe("calls: 1,200 in the report, 1,188 read by ALEAPP v2026.4.5")
  })
})
