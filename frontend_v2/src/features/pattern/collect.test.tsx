import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import { dossiersAPI } from "@/features/dossiers/api"
import { caseworkAPI } from "@/features/workspace/casework-api"
import { targetsNote } from "@/features/phones/collect-targets"
import { patternAPI, type Snapshot } from "./api"
import { KeepResult } from "./components/CollectBar"

describe("collecting from Patterns (07 section 6; CO-1 Patterns and Lanes cells)", () => {
  it("says how many targets are not offered instead of cutting the list silently", () => {
    expect(targetsNote({ shown: 200, total: 200 }, { shown: 12, total: 12 })).toBeNull()
    expect(targetsNote({ shown: 200, total: 245 }, { shown: 12, total: 12 })).toBe(
      "Offering the most recently changed 200 of 245 dossiers. Add from the dossier or Workspace for the others.")
  })

  it("keeps a result on the server, then offers Add to… for the kept result", async () => {
    const snap: Snapshot = { id: "pa_x", kind: "day", label: "Day view, Phone 1, 2024-05-03 00:00 to 2024-05-04 00:00 (UTC)",
      record_count: 7, stale: false, stale_words: null,
      snapshot: { summary_counts: { interaction: 2 }, window: { start: "2024-05-03T00:00:00+00:00", end: "2024-05-04T00:00:00+00:00", zone: "UTC" } } }
    const freeze = vi.spyOn(patternAPI, "freeze").mockResolvedValue(snap)
    vi.spyOn(dossiersAPI, "list").mockResolvedValue({ dossiers: [], total: 0, limit: 200, offset: 0 })
    vi.spyOn(caseworkAPI, "list").mockResolvedValue({ entries: [], total: 0 })
    render(<QueryClientProvider client={new QueryClient()}>
      <KeepResult caseId="c" origin="Added from Phone patterns, Day view" request={{ kind: "day", subject: "{}", date: "2024-05-03", zone: "UTC" }} />
    </QueryClientProvider>)
    fireEvent.click(screen.getByRole("button", { name: "Keep this result" }))
    expect(await screen.findByText(/Kept: Day view, Phone 1.*7 records behind it/)).toBeTruthy()
    expect(freeze).toHaveBeenCalledWith("c", { kind: "day", subject: "{}", date: "2024-05-03", zone: "UTC" })
    expect(screen.getByRole("button", { name: "Add to an interview" })).toBeTruthy()
  })
})

describe("key dates (04 section 8.6)", () => {
  it("reads a typed time in the zone it was given in, and refuses an unknown zone", async () => {
    const { zoned } = await import("./lanes-lib")
    expect(zoned("2024-05-03T01:52", "America/New_York")).toBe("2024-05-03T05:52:00.000Z")
    expect(zoned("2024-01-15T09:00", "America/New_York")).toBe("2024-01-15T14:00:00.000Z")
    expect(zoned("2024-05-03T01:52", "UTC")).toBe("2024-05-03T01:52:00.000Z")
    expect(zoned("2024-05-03T01:52", "Mars/Base")).toBeNull()
  })
})
