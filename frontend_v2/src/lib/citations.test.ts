import { describe, expect, it } from "vitest"
import { citationHrefs, parseCitation } from "./citations"

const ID = "0b6c2a1e-7d4f-4c1a-9e2b-5f3a8c9d0e11"

describe("one citation parser", () => {
  it("reads doc:// by id and page, and never turns a missing page into page 1", () => {
    expect(parseCitation(`doc://${ID}/4`)).toMatchObject({ scheme: "doc", target: ID, byName: false, page: 4 })
    expect(parseCitation(`doc://${ID}`)).toMatchObject({ scheme: "doc", byName: false, page: undefined })
    expect(parseCitation("doc://March%20statement.pdf/12")).toMatchObject({ target: "March statement.pdf", byName: true, page: 12 })
    expect(parseCitation("doc://March%20statement.pdf")).toMatchObject({ byName: true, page: undefined })
    expect(parseCitation("doc://report.pdf/0")).toMatchObject({ target: "report.pdf", page: undefined })
    expect(parseCitation("evidence://100%report.pdf")).toMatchObject({ target: "100%report.pdf", legacy: true })
  })

  it("reads txn://, the old Financial page payment link and rec://", () => {
    expect(parseCitation(`txn://${ID}`)).toMatchObject({ scheme: "txn", target: ID, legacy: false })
    expect(parseCitation(`/cases/c-1/financial?view=transactions&payment=${ID}`)).toBeNull() // a case id is a uuid
    const caseId = "9a9a9a9a-1b1b-4c1c-8d1d-2e2e2e2e2e2e"
    expect(parseCitation(`/cases/${caseId}/financial?view=transactions&payment=${ID}`)).toMatchObject({
      scheme: "txn", target: ID, legacy: true, linkedCaseId: caseId })
    expect(parseCitation(`rec://${ID}#Body`)).toMatchObject({ scheme: "rec", target: ID, field: "Body" })
    expect(parseCitation("txn://nope")).toBeNull()
    expect(parseCitation("https://example.com")).toBeNull()
    expect(parseCitation("javascript:alert(1)")).toBeNull()
  })

  it("lists each citation of a text once", () => {
    expect(citationHrefs(`[a](txn://${ID}) [b](txn://${ID}) [c](doc://x.pdf/2) [w](https://example.com)\n\n[d]: doc://${ID}/3`))
      .toEqual([`txn://${ID}`, "doc://x.pdf/2", `doc://${ID}/3`])
  })
})
