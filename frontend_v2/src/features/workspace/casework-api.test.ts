import { beforeEach, describe, expect, it, vi } from "vitest"
import { caseworkAPI } from "./casework-api"

describe("caseworkAPI", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("serializes indexed list filters and server pagination", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ entries: [], total: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await caseworkAPI.list("case 1", {
      entry_type: "theory",
      lifecycle_state: "investigating",
      confidence_min: 30,
      confidence_max: 65,
      author_user_id: "author-1",
      updated_since: "2026-08-01T00:00:00.000Z",
      sort_by: "confidence",
      sort_direction: "desc",
      limit: 25,
      offset: 50,
    })

    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain("/api/workspace/case%201/entries?")
    expect(url).toContain("entry_type=theory")
    expect(url).toContain("confidence_min=30")
    expect(url).toContain("confidence_max=65")
    expect(url).toContain("limit=25")
    expect(url).toContain("offset=50")
  })

  it("sends an editable finding draft during theory conversion", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ theory: {}, finding: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await caseworkAPI.convertToFinding("case-1", "theory-1", 4, "high", {
      title: "Confirmed transfer",
      body: "The records establish the transfer.",
    })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      expected_version: 4,
      significance: "high",
      title: "Confirmed transfer",
      body: "The records establish the transfer.",
    })
  })

  it("requests only explicitly selected attachment records", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await caseworkAPI.attachmentOptions(
      "case-1",
      "evidence",
      "",
      2,
      ["evidence-1", "evidence-2"],
    )

    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain("target_ids=evidence-1")
    expect(url).toContain("target_ids=evidence-2")
    expect(url).toContain("limit=2")
  })
})
