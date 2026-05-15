import { describe, expect, it } from "vitest"
import { dedupeCommsThreads } from "./thread-utils"
import type { CommsThread } from "../types"

function thread(overrides: Partial<CommsThread>): CommsThread {
  return {
    thread_id: "thread-1",
    thread_type: "chat",
    source_app: "WhatsApp",
    report_key: "report-a",
    participants: [],
    message_count: 1,
    last_activity: "2024-01-01T00:00:00Z",
    ...overrides,
  }
}

describe("dedupeCommsThreads", () => {
  it("keeps the richest duplicate thread and records merged ids", () => {
    const result = dedupeCommsThreads([
      thread({ thread_id: "thin", message_count: 4 }),
      thread({ thread_id: "rich", message_count: 9 }),
    ])

    expect(result).toHaveLength(1)
    expect(result[0].thread_id).toBe("rich")
    expect(result[0].merged_thread_ids).toEqual(["thin"])
  })

  it("collapses subset participant variants in the same app/report context", () => {
    const result = dedupeCommsThreads([
      thread({
        thread_id: "solo",
        participants: [{ key: "person-a" }],
        message_count: 10,
      }),
      thread({
        thread_id: "group",
        participants: [{ key: "person-a" }, { key: "person-b" }],
        message_count: 8,
      }),
    ])

    expect(result).toHaveLength(1)
    expect(result[0].thread_id).toBe("group")
    expect(result[0].merged_thread_ids).toEqual(["solo"])
  })

  it("does not merge different source apps", () => {
    const result = dedupeCommsThreads([
      thread({ thread_id: "sms", source_app: "SMS", participants: [{ key: "a" }] }),
      thread({
        thread_id: "signal",
        source_app: "Signal",
        participants: [{ key: "a" }, { key: "b" }],
      }),
    ])

    expect(result.map((item) => item.thread_id).sort()).toEqual(["signal", "sms"])
  })
})
