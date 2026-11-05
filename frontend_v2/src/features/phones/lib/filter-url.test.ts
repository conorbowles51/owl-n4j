import { describe, expect, it } from "vitest"
import { DEFAULT_VIEW, filterChips, filterChipWords, filterWordsOf, hasFilters, NO_APP, NO_FILTERS, PHONE_OWNER, viewFromSearch, viewToFilter, viewToSearch } from "./filter-url"

describe("Conversations filters (03 6.4)", () => {
  it("offers one deletion state and keeps the Phone summary's deleted=only link meaning both", () => {
    expect(viewToFilter("c", viewFromSearch("deleted=only"), "UTC").deleted_states).toEqual(["Deleted", "Trash"])
    const trash = viewFromSearch("deleted=trash")
    expect(trash.oneDeletion).toBe("Trash")
    expect(viewToFilter("c", trash, "UTC").deleted_states).toEqual(["Trash"])
    expect(viewToSearch(trash)).toBe("deleted=trash")
    expect(viewToFilter("c", viewFromSearch("deleted=deleted"), "UTC").deleted_states).toEqual(["Deleted"])
  })

  it("sends the apps, with no app recorded as null", () => {
    expect(viewToFilter("c", { ...DEFAULT_VIEW, apps: ["SyntheticApp", NO_APP] }, "UTC").apps).toEqual(["SyntheticApp", null])
  })

  it("says every filter as a chip that removes it, one date alone included", () => {
    const v = viewFromSearch("apps=SyntheticApp,not-recorded&directions=outgoing&from=2023-03-01&unreadable=exclude&attachment=only&q=cafe&exact=1&deleted=only")
    expect(filterChips(v).map((c) => c.text)).toEqual([
      "SyntheticApp", "App not recorded", "Outgoing", "From 2023-03-01", "Deleted or in trash only", "Without unreadable", "Has an attachment", 'Contains "cafe", exact characters',
    ])
    for (const c of filterChips(v)) {
      const left = filterChips({ ...v, ...c.clear })
      expect(left.map((x) => x.key)).not.toContain(c.key)
      expect(left).toHaveLength(filterChips(v).length - 1)
    }
    expect(filterChipWords(v)).toContain("Outgoing")
    expect(hasFilters({ ...v, ...NO_FILTERS })).toBe(false)
    expect(hasFilters(viewFromSearch("from=2023-03-01&to=2023-03-02"))).toBe(true)
    expect(hasFilters(viewFromSearch("kinds=call"))).toBe(true)
  })

  it("shows the only-with-a-time filter as a chip that Clear filters removes", () => {
    const v = viewFromSearch("from=2023-03-01&to=2023-03-02&notime=0")
    expect(filterChips(v).map((c) => c.text)).toEqual(["Only those with a time"])
    expect({ ...v, ...NO_FILTERS }.noTime).toBe(true)
    expect(hasFilters(viewFromSearch("notime=0"))).toBe(true)
  })

  it("names every narrowing in the words kept with a copy, an export or a saved view", () => {
    expect(filterWordsOf(viewFromSearch("from=2023-03-01&to=2023-03-02&kinds=call&directions=outgoing"))).toBe("2023-03-01 to 2023-03-02, call, Outgoing")
  })

  it("makes a date range days in the stated zone", () => {
    const f = viewToFilter("c", viewFromSearch("from=2023-03-14&to=2023-03-14"), "Asia/Tokyo")
    expect(f.from_instant).toBe("2023-03-13T15:00:00.000Z")
    expect(f.to_instant).toBe("2023-03-14T14:59:59.999Z")
  })
})

describe("Conversations view in the URL (03 6.4)", () => {
  it("round-trips every filter and leaves defaults out", () => {
    const v = { ...DEFAULT_VIEW, thread: "chat:x:1", people: ["phone:+12025550143", "phone:+12025550188"], mode: "between" as const,
      phones: ["p1"], from: "2023-03-01", to: "2023-03-31", kinds: ["message"], apps: ["WhatsApp"], deleted: true,
      text: "café", everyCopy: true, allChannels: true, sort: "newest_first" as const, threadSort: "volume" as const,
      hl: "jose", hlExact: true, at: "v2", selection: "sel-1" }
    const s = viewToSearch(v)
    expect(viewFromSearch(s)).toEqual(v)
    expect(viewToFilter("c", v, "UTC").selection).toBe("sel-1") // a saved selection link opens its frozen records
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
    // Between with one person is between that person and the owner of each phone (07 J-3, Between A and B);
    // with three people it reads as Involving and still filters by them (review of 03-3).
    const one = viewToFilter("c", { ...v, people: ["a"] }, "UTC")
    expect(one.participants).toEqual(["a", PHONE_OWNER])
    expect(one.participant_mode).toBe("between")
    expect(one.group_scope).toBe("include_groups")
    const three = viewToFilter("c", { ...v, people: ["a", "b", "d"] }, "UTC")
    expect(three.participants).toEqual(["a", "b", "d"])
    expect(three.participant_mode).toBe("any")
    expect(three.group_scope).toBeUndefined()
  })

  it("the thread list filter ignores the chosen thread; a fixed phone stays out of the URL", () => {
    const v = viewFromSearch("thread=t1", "p9")
    expect(v.phones).toEqual(["p9"])
    expect(viewToFilter("c", v, "UTC", false).threads).toBeUndefined()
    expect(viewToFilter("c", v, "UTC").threads).toEqual(["t1"])
    expect(viewToSearch(v, "p9")).toBe("thread=t1")
  })

  it("a search's marks and its message ride in the URL but never filter the thread (S-8)", () => {
    const v = viewFromSearch("thread=t1&at=v2&hl=jose&hlexact=1")
    expect([v.hl, v.hlExact, v.at]).toEqual(["jose", true, "v2"])
    expect(viewToFilter("c", v, "UTC").text).toBeUndefined()
  })
})
