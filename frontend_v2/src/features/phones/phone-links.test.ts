import { expect, it } from "vitest"
import {
  isPhoneIdentityNode,
  phoneIdentityDecisionHref,
  phoneLinkHref,
  phoneLinkSummary,
  phoneTimeWithZone,
  significantOfferedForLink,
} from "./phone-links"

it("opens every phone link type at its phone route, and nothing for other types (07 6.4 item 11)", () => {
  const anchor = { extraction_id: "ext 1", record_type: "messages" }
  expect(phoneLinkHref("c1", { target_type: "phone_record", target_id: "r/1", source_anchor: anchor }))
    .toBe("/cases/c1/phones/ext%201/records/messages?record=r%2F1")
  expect(phoneLinkHref("c1", { target_type: "phone_record", target_id: "r1" })).toBe("/cases/c1/phones?record=r1")
  expect(phoneLinkHref("c1", { target_type: "phone_extraction", target_id: "e1" })).toBe("/cases/c1/phones/e1")
  expect(phoneLinkHref("c1", { target_type: "phone_analysis", target_id: "pa_1", source_anchor: { kind: "co_location" } }))
    .toBe("/cases/c1/phone-patterns?analysis=co_location&snapshot=pa_1")
  expect(phoneLinkHref("c1", { target_type: "statement_check", target_id: "sc1" })).toBe("/cases/c1/phone-patterns?check=sc1")
  for (const type of ["phone_file", "phone_thread", "phone_identity", "phone_selection", "phone_view", "statement_check"]) {
    expect(phoneLinkHref("c1", { target_type: type, target_id: "x" })).toMatch(/^\/cases\/c1\/phone/)
  }
  expect(phoneLinkHref("c1", { target_type: "evidence", target_id: "x" })).toBeNull()
})

it("shows label, app, the recorded time with its zone, and badges", () => {
  const summary = phoneLinkSummary({
    target_type: "phone_record", target_id: "r1", target_label: "Message",
    source_anchor: { app: "WhatsApp", instant: "2024-03-01T23:30:00-05:00", zone: "America/New_York" },
    metadata: { badges: ["Deleted", "Mapped by the system, not yet confirmed"] },
  })
  expect(summary).toEqual({ label: "Message", kind: "Phone record", app: "WhatsApp",
    time: "2024-03-01 23:30 (America/New_York)", badges: ["Deleted", "Mapped by the system, not yet confirmed"] })
  expect(phoneTimeWithZone({ target_type: "phone_record", target_id: "r", source_anchor: { instant: "2024-03-01T04:30:00Z" } }))
    .toBe("2024-03-01 04:30 (UTC)")
  expect(phoneTimeWithZone({ target_type: "phone_record", target_id: "r", source_anchor: { instant: "2024-03-01T04:30:00" } }))
    .toBe("2024-03-01 04:30 (zone not recorded)")
  expect(phoneLinkSummary({ target_type: "phone_selection", target_id: "s", metadata: { record_count: 12345 } }).badges)
    .toEqual(["12,345 records"])
})

it("routes a phone identity to the identity decision and offers Significant only for graph keys (07 6.4 item 12)", () => {
  expect(isPhoneIdentityNode("PhoneIdentity")).toBe(true)
  expect(isPhoneIdentityNode("Person")).toBe(false)
  expect(phoneIdentityDecisionHref("c1", "id:1")).toBe("/cases/c1/phone-review?decision=link_phone_identity&identity=id%3A1")
  // from the Graph the node key carries the projection's prefix; the decision takes the identity key itself (CO-13)
  expect(phoneIdentityDecisionHref("c1", "phone-identity:app:telegram:id:@synthetic_ben"))
    .toBe("/cases/c1/phone-review?decision=link_phone_identity&identity=app%3Atelegram%3Aid%3A%40synthetic_ben")
  expect(["graph_entity", "phone_identity", "phone_extraction"].every(significantOfferedForLink)).toBe(true)
  expect(["phone_record", "phone_file", "phone_thread", "phone_selection", "phone_analysis"].some(significantOfferedForLink)).toBe(false)
})

it("opens a kept approach result on its analysis screen", () => {
  expect(phoneLinkHref("c1", { target_type: "phone_analysis", target_id: "pa_9", source_anchor: { kind: "analysis_result", approach: "message_reconciliation" } }))
    .toBe("/cases/c1/phone-analyses/messages?kept=pa_9")
})
