import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { patternAPI, type Evaluation, type EvaluationItem, type GroupEvents } from "./api"
import { RoleList } from "./components/StatementCheckPanel"
import { setApartWords, usualLast } from "./lanes-lib"

function item(ordinal: number, over: Partial<EvaluationItem> = {}): EvaluationItem {
  return { ordinal, role: "supporting", ref_kind: "window_piece", ref_id: `e1:${ordinal}`, strength: "moderate",
    reason_code: "data_no_interaction", explanation: "The phone was recording and shows no use.", record_uid: null,
    extraction_id: "e1", at_utc: "2023-03-14T23:00:00+00:00", end_utc: null, display: {}, disputed: null, ...over }
}

function evaluation(items: EvaluationItem[]): Evaluation {
  return { evaluation_id: "ev1", items, total_items: items.length } as unknown as Evaluation
}

describe("statement check items", () => {
  it("lists 200 of a long role at a time, with the count, and shows the rest on request", () => {
    const items = Array.from({ length: 450 }, (_, n) => item(n))
    render(<RoleList caseId="c" claimId="cl" ev={evaluation(items)} role="supporting" title="Supports" onDispute={() => {}} />)
    expect(screen.getByText("Supports (450)")).toBeTruthy()
    expect(screen.getAllByText("The phone was recording and shows no use.")).toHaveLength(200)
    expect(screen.getByText(/Showing 200 of 450\./)).toBeTruthy()
    fireEvent.click(screen.getByText("Show 200 more"))
    fireEvent.click(screen.getByText("Show 50 more"))
    expect(screen.getAllByText("The phone was recording and shows no use.")).toHaveLength(450)
    expect(screen.queryByText(/Showing/)).toBeNull()
  })

  it("opens a counted group's events and says when the phone's readings changed since the check", async () => {
    const group = item(3, { role: "context", ref_kind: "event_group", reason_code: "passive", strength: null,
      explanation: "2 events in this hour. Recorded by the phone without anyone using it.", display: { count: 2, hour_utc: "2023-03-14T23:00:00+00:00" } })
    const page: GroupEvents = { ordinal: 3, stored_count: 2, total: 3, cursor: 0, limit: 1000, returned: 3, next_cursor: null,
      changed_since_check: true, items: [1, 2, 3].map((n) => ({ activity_event_id: n, at_utc: `2023-03-14T23:0${n}:00+00:00`, end_utc: null,
        record_uid: null, field_path: null, display: { type: "DeviceEvent", field: "StartTime", meaning: "event_instant", source_app: null,
          activity_class: "passive", actor: "owner" } })) }
    const spy = vi.spyOn(patternAPI, "groupEvents").mockResolvedValue(page)
    render(<RoleList caseId="c" claimId="cl" ev={evaluation([group])} role="context" title="Context" onDispute={() => {}} />)
    fireEvent.click(screen.getByText("Show the 2 events"))
    expect(await screen.findByText(/3 events now, 2 when checked/)).toBeTruthy()
    expect(screen.getAllByText("DeviceEvent, StartTime")).toHaveLength(3)
    expect(screen.getByText(/Showing 3 of 3\./)).toBeTruthy()
    expect(spy).toHaveBeenCalledWith("c", "cl", "ev1", 3, 0)
  })
})

describe("usual span (04 decision 38)", () => {
  it("opens on the usual span's last day and says how many events are set apart", () => {
    const span = { first: "2022-07-16", last: "2024-10-23", set_apart: 1129, set_apart_first: "1953-08-07T00:00:00+00:00",
      set_apart_last: "2057-08-30T10:00:00+00:00" }
    expect(usualLast({ last: "2057-08-30T10:00:00+00:00", usual_span: span })).toBe("2024-10-23")
    expect(usualLast({ last: "2024-12-05T08:00:00+00:00", usual_span: null })).toBe("2024-12-05")
    expect(setApartWords("Phone 1", span)).toBe("Phone 1: 1,129 events lie on dates set apart from the rest (1953-08-07 to " +
      "2057-08-30, UTC). The views open on the usual span, 2022-07-16 to 2024-10-23; any date can still be chosen.")
    expect(setApartWords("Phone 1", { ...span, set_apart: 0 })).toBeNull()
  })
})
