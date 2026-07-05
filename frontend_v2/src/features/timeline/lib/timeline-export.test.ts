import { describe, expect, it } from "vitest"
import {
  buildTimelineExportPayload,
  defaultTimelineExportFields,
  timelineDateSpan,
} from "./timeline-export"
import type { TimelineEvent, TimelineView } from "../api"

function event(key: string, date = "2024-01-01"): TimelineEvent {
  return {
    key,
    name: key,
    type: "Event",
    date,
    time: null,
    amount: null,
    summary: null,
    notes: null,
    connections: [],
  }
}

const view: TimelineView = {
  id: "view-1",
  case_id: "case-1",
  title: "Focused view",
  visibility: "case",
  filter_snapshot: {},
  export_defaults: {},
  event_count: 2,
  events: [],
}

describe("timeline export helpers", () => {
  it("builds a fixed-view export payload without sending browser event keys", () => {
    const payload = buildTimelineExportPayload({
      caseId: "case-1",
      source: "view",
      format: "pdf",
      detailLevel: "standard",
      fields: defaultTimelineExportFields("standard"),
      activeView: view,
      filteredEvents: [event("a"), event("b")],
      selectedKeys: new Set(["a"]),
      title: "",
    })

    expect(payload.view_id).toBe("view-1")
    expect(payload.event_keys).toEqual([])
    expect(payload.title).toBe("Focused view")
  })

  it("builds a selected-event export payload from curation selection", () => {
    const payload = buildTimelineExportPayload({
      caseId: "case-1",
      source: "selection",
      format: "csv",
      detailLevel: "compact",
      fields: defaultTimelineExportFields("compact"),
      activeView: view,
      filteredEvents: [event("a"), event("b")],
      selectedKeys: new Set(["b", "a"]),
      title: "Selected",
    })

    expect(payload.view_id).toBeNull()
    expect(payload.event_keys).toEqual(["b", "a"])
    expect(payload.fields?.summary).toBe(false)
  })

  it("formats the preview date span", () => {
    expect(timelineDateSpan([event("a", "2024-01-02"), event("b", "2024-01-05")])).toBe(
      "2024-01-02 to 2024-01-05"
    )
  })
})
