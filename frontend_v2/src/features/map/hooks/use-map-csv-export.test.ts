import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { MapLocation } from "./use-map-data"
import { useMapCsvExport } from "./use-map-csv-export"

describe("useMapCsvExport", () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("exports the current map locations with v1 CSV columns", async () => {
    let exportedBlob: Blob | undefined
    let link: HTMLAnchorElement | undefined

    const createObjectURL = vi.fn((blob: Blob | MediaSource) => {
      exportedBlob = blob as Blob
      return "blob:map-locations"
    })
    const revokeObjectURL = vi.fn()

    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    })

    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, "createElement").mockImplementation(
      ((tagName: string, options?: ElementCreationOptions) => {
        const element = originalCreateElement(
          tagName as keyof HTMLElementTagNameMap,
          options
        )

        if (tagName.toLowerCase() === "a") {
          link = element as HTMLAnchorElement
          vi.spyOn(link, "click").mockImplementation(() => undefined)
        }

        return element
      }) as typeof document.createElement
    )

    const locations: MapLocation[] = [
      {
        key: "loc-1",
        name: 'Central "Hub", North',
        type: "location",
        latitude: 51.501,
        longitude: -0.141,
        location_formatted: "10 Downing St, London",
        location_raw: 'The "safe" house',
        geocoding_confidence: "high",
        date: "2026-07-01",
        summary: 'Witness saw Alice, then said "urgent"',
        connections: [
          {
            key: "p1",
            name: "Alice",
            type: "person",
            relationship: "visited",
          },
          {
            key: "p2",
            name: "Bob",
            type: "person",
            relationship: "met at",
          },
        ],
      },
      {
        key: "loc-2",
        name: "Warehouse",
        type: "event",
        latitude: 48.8566,
        longitude: 2.3522,
      },
    ]

    const { result } = renderHook(() => useMapCsvExport())

    act(() => {
      result.current.exportCSV(locations, "case-123")
    })

    expect(link?.download).toBe("locations-case-123.csv")
    expect(link?.href).toBe("blob:map-locations")
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:map-locations")

    expect(exportedBlob).toBeDefined()
    const csv = await exportedBlob!.text()
    const rows = csv.split("\n")

    expect(rows[0]).toBe(
      "Name,Type,Latitude,Longitude,Location (Formatted),Location (Raw),Geocoding Confidence,Date,Summary,Connections"
    )
    expect(rows[1]).toBe(
      '"Central ""Hub"", North",location,51.501,-0.141,"10 Downing St, London","The ""safe"" house",high,2026-07-01,"Witness saw Alice, then said ""urgent""",Alice (visited); Bob (met at)'
    )
    expect(rows[2]).toBe("Warehouse,event,48.8566,2.3522,,,,,,")
  })
})
