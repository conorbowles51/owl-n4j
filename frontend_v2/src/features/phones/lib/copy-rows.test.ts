import { describe, expect, it } from "vitest"
import { labelText } from "./labels"
import { FILE_OUTCOME_BADGE, rowBadges } from "./badges"
import { buildSegments, itemCount, segmentAt } from "../hooks/use-stream"
import type { ParticipantLabelData, StreamIndex, StreamRow } from "../schemas"
import { rowText, rowsHtml, rowsText } from "./copy-rows"

const owner: ParticipantLabelData = {
  identity_key: "phone:+12025550100", name: null, name_basis: "none", is_owner: true, owner_basis: "extracted", phone_label: "C3",
  identifier: { kind: "phone", display: "+1 202-555-0100" }, case_names: [],
}
const maria: ParticipantLabelData = {
  identity_key: "phone:+12025550143", name: "Maria Lopez", name_basis: "contact_on_this_phone", is_owner: false, owner_basis: null,
  identifier: { kind: "phone", display: "+1 202-555-0143" }, case_names: [],
}

export function row(over: Partial<StreamRow> = {}): StreamRow {
  return {
    event_uid: "e1", record_uid: "r1", kind: "message", phone: { extraction_id: "x", label: "C3" }, app: "WhatsApp",
    thread: null, direction: "incoming",
    time: { instant: "2023-03-14T19:07:12Z", row: "3:07 PM", full: "Tue, Mar 14, 2023, 3:07:12 PM EDT", offset_present: true, time_field: "TimeStamp" },
    from: maria, to: [owner], body: "Line one\nLine two", subject: null, call: null, attachments: [], flags: [],
    copies: { count: 1, record_uids: ["r1"], apps: ["WhatsApp"] }, owner_read: { date_read: null, date_played: null },
    interpretation_level: "reviewed", line: "Maria Lopez (+1 202-555-0143) -> Owner of C3 (+1 202-555-0100)", ...over,
  }
}

describe("copy rows (03 3.7, A13, A2)", () => {
  it("states a forward apart from its sender, and a reply with or without its original (03 6.6)", () => {
    const forwarded = rowText(row({ forward: { original_sender: owner, time_created: "Mon, Mar 1, 2023" } }))
    expect(forwarded).toContain("Maria Lopez (+1 202-555-0143) -> Owner of C3")
    expect(forwarded).toContain("[Forwarded. First written by Owner of C3 (+1 202-555-0100), Mon, Mar 1, 2023]")
    expect(rowText(row({ forward: { original_sender: null, time_created: null } }))).toContain("[Forwarded. The report does not say who first wrote it]")
    expect(rowText(row({ replies: [{ kind: "reply", original_id: "AB12", state: "not_in_extraction", target: null }] }))).toContain("[Replying to a message that is not in this extraction (the report's id: AB12)]")
    const target = { event_uid: "e0", record_uid: "r0", thread_key: "t", thread_title: "Family", same_thread: false, kind: "message", from: maria, time: "Tue, Mar 14", excerpt: "first", chars: 5, subject: null, flags: [] }
    expect(rowText(row({ replies: [{ kind: "quote", original_id: "AB12", state: "found", target }] }))).toContain("[Quoting Maria Lopez (+1 202-555-0143), Tue, Mar 14 in Family: first]")
    expect(rowText(row({ replies: [{ kind: "reply", original_id: "AB12", state: "found", target: { ...target, chars: 900 } }] }))).toContain("in Family: first…]")
  })

  it("writes one line per event with day, 12-hour time, zone, phone, app, both labels and the full body", () => {
    expect(rowText(row())).toBe(
      "Tue, Mar 14, 2023, 3:07:12 PM EDT | C3 | WhatsApp | Maria Lopez (+1 202-555-0143) -> Owner of C3 (+1 202-555-0100) | Line one\n  Line two",
    )
  })

  it("lists attachments and flags, and ends with the filter and zone", () => {
    const r = row({ body: "x", flags: ["Deleted"], attachments: [{ file_uid: "f", filename: "a.jpg", category: "Image", verification: "missing", mechanism: "attachment_field" }] })
    const text = rowsText([r], "Synthetic case", "between Maria and the owner", "Eastern Time")
    expect(text).toContain("| x [attachment: a.jpg, Image] [Deleted]")
    expect(text.trim().split("\n").pop()).toBe("Copied from Loupe, case Synthetic case, filter: between Maria and the owner, times in Eastern Time.")
  })

  it("writes an HTML table with the same columns", () => {
    const html = rowsHtml([row(), row({ event_uid: "e2", body: "<b>" })], "C", "none", "UTC")
    expect(html).toMatch(/^<table><thead><tr><th>Time<\/th><th>Phone<\/th><th>App<\/th><th>From and to<\/th>/)
    expect(html.match(/<tr>/g)?.length).toBe(3)
    expect(html).toContain("&lt;b&gt;")
    expect(html).toContain("Line one<br>Line two")
  })

  it("a call copies its words", () => {
    expect(rowText(row({ kind: "call", body: null, call: { duration_s: 63, status: "Established", video: false, words: "Call, 1 min 3 s, answered" } }))).toContain(
      "| Call, 1 min 3 s, answered",
    )
  })
})

describe("participant labels (3.3, A2, C-6, P-3)", () => {
  it("covers every row of the table", () => {
    expect(labelText(maria)).toBe("Maria Lopez (+1 202-555-0143)")
    expect(labelText({ ...maria, name: null, name_basis: "none" })).toBe("(no name on this phone) (+1 202-555-0143)")
    expect(labelText({ ...maria, name: "Maria L", identifier: { kind: "app_user", subkind: "whatsapp_jid", display: "5521@s.whatsapp.net" } })).toBe(
      "Maria L (WhatsApp id 5521@s.whatsapp.net)",
    )
    expect(labelText({ ...maria, identifier: { kind: "email", display: "maria@example.com" } })).toBe("Maria Lopez (maria@example.com)")
    expect(labelText(owner)).toBe("Owner of C3 (+1 202-555-0100)")
    expect(labelText({ ...owner, name: "N" })).toBe("Owner of C3: N (+1 202-555-0100)")
    expect(labelText({ ...owner, identifier: null })).toBe("Owner of C3 (number not in the extraction)")
    expect(labelText({ ...owner, owner_basis: "manual" })).toBe("Owner of C3 [Owner set by a person] (+1 202-555-0100)")
    expect(labelText({ ...maria, identifier: { kind: "other", display: "12345", normalised: false } })).toBe("Maria Lopez (12345)")
  })
})

describe("state badges (3.5, C3: all seven file outcomes)", () => {
  it("has a badge for every outcome but a match", () => {
    expect(Object.keys(FILE_OUTCOME_BADGE).sort()).toEqual(["empty_placeholder", "match", "mismatch", "missing", "no_hash", "no_local_path", "size_mismatch"])
    for (const [outcome, words] of Object.entries(FILE_OUTCOME_BADGE)) {
      const badges = rowBadges(row({ attachments: [{ file_uid: "f", filename: "a", category: null, verification: outcome, mechanism: "tagged_file" }] }))
      if (outcome === "match") expect(badges).toEqual([])
      else expect(badges.map((b) => b.words)).toEqual([words])
    }
  })

  it("orders by priority and names copies", () => {
    const b = rowBadges(row({ flags: ["Deleted", "Mapped by the system, not yet confirmed"], copies: { count: 3, record_uids: ["a", "b", "c"], apps: ["A", "B", "C"] } }))
    expect(b.map((x) => x.words)).toEqual(["Mapped by the system, not yet confirmed", "Deleted", "Found 3 times"])
  })
})

describe("stream segments (3.1 rule 5)", () => {
  const index = {
    items: [
      { day: "2023-03-14", count: 2, offsets: "UTC-4", header: "Tuesday, March 14, 2023", zone_label: "Eastern Time (UTC-4)" },
      { day: "2023-03-15", count: 3, offsets: "UTC-4", header: "Wednesday, March 15, 2023", zone_label: "Eastern Time (UTC-4)" },
    ],
    no_time_count: 1,
    no_time_position: "last",
  } as unknown as StreamIndex
  it("places the undated group last oldest first and first newest first", () => {
    const segs = buildSegments(index)
    expect(segs.map((s) => [s.day, s.start, s.count])).toEqual([["2023-03-14", 0, 2], ["2023-03-15", 3, 3], [null, 7, 1]])
    expect(itemCount(segs)).toBe(9)
    expect(segmentAt(segs, 4)).toBe(1)
    expect(segmentAt(segs, 8)).toBe(2)
    const first = buildSegments({ ...index, no_time_position: "first" } as StreamIndex)
    expect(first[0].header).toBe("No time recorded")
  })
})
