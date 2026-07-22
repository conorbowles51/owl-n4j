import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { graphAPI } from "./api"

describe("graphAPI edit helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      removeItem: vi.fn(),
      setItem: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("sends case-scoped node edit payloads", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true, updated_fields: [], changes: {} }), {
        status: 200,
      })
    )

    await graphAPI.updateNode("event-1", {
      case_id: "case-1",
      category: "Communication",
      properties: { date: "2024-01-02", time: "14:30" },
      source_view: "timeline",
    })

    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/graph/node/event-1")
    expect(options?.method).toBe("PUT")
    expect(JSON.parse(options?.body as string)).toEqual({
      case_id: "case-1",
      category: "Communication",
      properties: { date: "2024-01-02", time: "14:30" },
      source_view: "timeline",
    })
  })

  it("requests the Significant graph as a server-side projection", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ nodes: [], links: [] }), { status: 200 })
    )

    await graphAPI.getGraph({ case_id: "case-1", scope: "significant" })

    const [url] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toContain("case_id=case-1")
    expect(url).toContain("scope=significant")
    expect(url).toContain("lightweight=true")
  })

  it("maps lightweight source counts for the table projection", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          nodes: [
            {
              key: "person-1",
              name: "Victoria Blackwood QC",
              type: "Person",
              source_count: 2,
            },
          ],
          links: [],
        }),
        { status: 200 }
      )
    )

    const graph = await graphAPI.getGraph({ case_id: "case-1" })

    expect(graph.nodes[0].source_count).toBe(2)
  })

  it("scopes graph analysis to the induced Significant graph", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ results: [] }), { status: 200 })
    )

    await graphAPI.getPageRank(
      "case-1",
      undefined,
      undefined,
      undefined,
      undefined,
      "significant"
    )

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(JSON.parse(options?.body as string)).toMatchObject({
      case_id: "case-1",
      scope: "significant",
    })
  })

  it("supports geocode preview without applying immediately", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          latitude: 51.5,
          longitude: -0.12,
          formatted_address: "London, UK",
          confidence: "high",
          applied: false,
        }),
        { status: 200 }
      )
    )

    await graphAPI.geocodeNode("loc-1", "case-1", "London", false)

    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/graph/node/loc-1/geocode?apply=false")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual({
      case_id: "case-1",
      address: "London",
    })
  })

  it("exposes graph source files in node details", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          key: "person-1",
          name: "Victoria Blackwood",
          type: "Person",
          properties: {
            source_files: ["registry.pdf", "report.pdf", "registry.pdf"],
          },
          connections: [],
        }),
        { status: 200 }
      )
    )

    const detail = await graphAPI.getNodeDetails("person-1", "case-1")

    expect(detail.sources).toEqual([
      { fileId: "registry.pdf", fileName: "registry.pdf" },
      { fileId: "report.pdf", fileName: "report.pdf" },
    ])
  })
})
