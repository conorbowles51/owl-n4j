import { describe, expect, it } from "vitest"
import { DEFAULT_VIEW, viewFromSearch, viewToFilter, viewToSearch } from "./filter-url"

describe("Conversations view in the URL (03 6.4)", () => {
  it("round-trips every filter and leaves defaults out", () => {
    const v = { ...DEFAULT_VIEW, thread: "chat:x:1", people: ["phone:+12025550143", "phone:+12025550188"], mode: "between" as const,
      phones: ["p1"], from: "2023-03-01", to: "2023-03-31", kinds: ["message"], apps: ["WhatsApp"], deleted: true,
      text: "café", everyCopy: true, allChannels: true, sort: "newest_first" as const, threadSort: "volume" as const }
    const s = viewToSearch(v)
    expect(viewFromSearch(s)).toEqual(v)
    expect(viewToSearch(DEFAULT_VIEW)).toBe("")
  })

  it("builds the stream filter the backend reads", () => {
    const v = viewFromSearch("people=a,b&mode=between&channels=all&from=2023-03-14&to=2023-03-14&deleted=exclude&copies=all")
    const f = viewToFilter("c", v, "America/New_York")
    expect(f.participant_mode).toBe("between")
    expect(f.group_scope).toBe("include_groups")
    expect(f.from_instant).toBe("2023-03-14T04:00:00.000Z")
    expect(f.to_instant).toBe("2023-03-15T03:59:59.999Z")
    expect(f.deleted_states).toEqual([null, "Intact", "Unknown"])
    expect(f.collapse_copies).toBe(false)
    expect(viewToFilter("c", { ...v, people: ["a"] }, "UTC").participants).toBeUndefined() // between needs two
  })

  it("the thread list filter ignores the chosen thread; a fixed phone stays out of the URL", () => {
    const v = viewFromSearch("thread=t1", "p9")
    expect(v.phones).toEqual(["p9"])
    expect(viewToFilter("c", v, "UTC", false).threads).toBeUndefined()
    expect(viewToFilter("c", v, "UTC").threads).toEqual(["t1"])
    expect(viewToSearch(v, "p9")).toBe("thread=t1")
  })
})
