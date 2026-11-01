import { describe, expect, it } from "vitest"
import FIELDS from "./ux-event-fields.json"
import { flushUx, refusal, refusedCountForTest, resetUxForTest, startJourney, trackUx, type UxEvent } from "./ux-events"

// Invented values of each kind of case material; none may pass in any field (07 10.2).
const CASE_MATERIAL = ["Jordan Avery", "+12025550143", "meet at the dock at 9", "12 Harbour Road", "40.7128,-74.0060",
  "EXH-0042", "jordan@example.com", 40.7128]

function capture() {
  const posts: { case_id: string | null; events: UxEvent[] }[] = []
  resetUxForTest((body) => posts.push(body))
  return posts
}

describe("ux events: allowed fields only", () => {
  it("refuses case material in every field of every event", () => {
    for (const [kind, fields] of Object.entries(FIELDS.events)) {
      for (const f of fields) {
        for (const v of CASE_MATERIAL) {
          const spec = (FIELDS.field_types as Record<string, { number?: number[] }>)[f]
          if (typeof v === "number" && spec.number) continue // a bare number is a valid millisecond count
          expect(refusal({ event: kind, [f]: v }), `${kind}.${f}=${v}`).not.toBeNull()
        }
      }
    }
  })

  it("refuses unknown fields and events, and sends nothing for them", () => {
    const posts = capture()
    expect(trackUx(null, { event: "search_empty", screen: "search", query: "x" } as unknown as UxEvent)).toBe(false)
    expect(trackUx(null, { event: "page_text" } as unknown as UxEvent)).toBe(false)
    flushUx()
    expect(posts).toEqual([])
    expect(refusedCountForTest()).toBe(2)
  })

  it("every payload a journey sends passes the allowed-field list", () => {
    const posts = capture()
    let t = 0
    const j = startJourney("4aa79795-1076-4c75-985f-784936abb71f", "J-3", "conversations", () => (t += 1000))
    j.action()
    j.step("phone-records")
    j.complete()
    j.abandon() // ignored after completion
    trackUx("not-a-case", { event: "collect", target_kind: "dossier", count: 12, added: 10, skipped: 2, ms: 840.4 })
    trackUx(null, { event: "wait", screen: "phones", ms: 2400, panel: true })
    flushUx()
    const sent = posts.flatMap((p) => p.events)
    expect(sent.map((e) => e.event)).toEqual(["journey_start", "journey_step", "journey_complete", "collect", "wait"])
    for (const e of sent) expect(refusal(e)).toBeNull()
    expect(posts[0].case_id).toBe("4aa79795-1076-4c75-985f-784936abb71f")
    expect(posts[1].case_id).toBeNull() // an address that is not a case id is never sent
    expect(sent[2]).toEqual({ event: "journey_complete", journey: "J-3", ms: 2000, actions: 1 })
    const text = JSON.stringify(posts)
    for (const v of CASE_MATERIAL) if (typeof v === "string") expect(text).not.toContain(v)
  })
})
