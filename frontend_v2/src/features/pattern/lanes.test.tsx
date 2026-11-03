import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { Lanes } from "./components/Lanes"
import { bandsFromHours } from "./lanes-lib"

const sources = import.meta.glob(["/src/**/*.tsx", "!/src/**/*.test.tsx", "!/src/**/*.stories.tsx"], {
  query: "?raw", import: "default", eager: true,
}) as Record<string, string>

describe("the shared Lanes component (04 section 8.6, 07 J-5)", () => {
  it("draws one region per lane, its count, and No data apart from no use seen", () => {
    const onSpan = vi.fn()
    const hours = [
      { hour_utc: "2023-03-14T23:00:00Z", state: "data_no_interaction", words: "Phone recording, no use seen" },
      { hour_utc: "2023-03-15T00:00:00Z", state: "no_data", words: "No data" },
    ]
    render(<Lanes start="2023-03-14T23:00:00Z" end="2023-03-15T01:00:00Z" zone="America/New_York" zoneBasis="case_setting" span="1h" onSpan={onSpan}
      rows={[{ id: "p", label: "C1", bands: bandsFromHours(hours), marks: [{ key: "m", at: "2023-03-14T23:30:00Z", label: "message", tone: "strong" }] },
        { id: "case", label: "Case events", marks: [] },
        { id: "money", label: "Payments", marks: [], allDay: [{ key: "t", label: "12.00 USD", detail: "Posted date; the purchase may be earlier." }] }]} />)
    expect(screen.getByRole("region", { name: "Lane: C1" })).toBeTruthy()
    expect(screen.getByRole("region", { name: "Lane: Case events" })).toBeTruthy()
    expect(screen.getByText("No data")).toBeTruthy()
    expect(screen.getByText("Phone recording, no use seen")).toBeTruthy()
    expect(screen.getByText(/case zone/)).toBeTruthy()
    expect(screen.getByText("12.00 USD (all day)")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "±6 h" }))
    expect(onSpan).toHaveBeenCalledWith("6h")
  })

  it("hides device events and sensor readings by default, counts them, and shows them on one click", () => {
    render(<Lanes start="2023-03-14T00:00:00Z" end="2023-03-15T00:00:00Z" zone="UTC"
      rows={[{ id: "comm", label: "Messages and calls", marks: [] },
        { id: "device_state", label: "Device state", total: 12, collapsible: true, marks: [] },
        { id: "passive", label: "Recorded without use", total: 3, collapsible: true, marks: [] }]} />)
    expect(screen.getByText("15 device events and sensor readings hidden.")).toBeTruthy()
    expect(screen.queryByRole("region", { name: "Lane: Device state" })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Show" }))
    expect(screen.getByRole("region", { name: "Lane: Device state" })).toBeTruthy()
    expect(screen.getByText("Showing 15 device events and sensor readings.")).toBeTruthy()
  })

  it("merges neighbouring hours of one state into one band", () => {
    const b = bandsFromHours([
      { hour_utc: "2023-03-14T01:00:00Z", state: "no_data", words: "No data" },
      { hour_utc: "2023-03-14T02:00:00Z", state: "no_data", words: "No data" },
      { hour_utc: "2023-03-14T03:00:00Z", state: "interaction", words: "Use seen" },
    ])
    expect(b.map((x) => [x.state, x.start, x.end])).toEqual([
      ["no_data", "2023-03-14T01:00:00.000Z", "2023-03-14T03:00:00.000Z"],
      ["interaction", "2023-03-14T03:00:00.000Z", "2023-03-14T04:00:00.000Z"],
    ])
  })

  it("shades a not-observed hour that holds records apart from No data, in the lane and in its legend (followups m110312500118802)", () => {
    const hours = [
      { hour_utc: "2023-11-08T09:00:00Z", state: "no_data", words: "No data" },
      { hour_utc: "2023-11-08T10:00:00Z", state: "no_data", has_records: true, words: "No continuous recording; records this hour" },
      { hour_utc: "2023-11-08T11:00:00Z", state: "no_data", words: "No data" },
    ]
    const bands = bandsFromHours(hours)
    expect(bands.map((b) => [b.start, !!b.hasRecords])).toEqual([
      ["2023-11-08T09:00:00.000Z", false], ["2023-11-08T10:00:00.000Z", true], ["2023-11-08T11:00:00.000Z", false]])
    render(<Lanes start="2023-11-08T09:00:00Z" end="2023-11-08T12:00:00Z" zone="UTC" rows={[{ id: "p", label: "Phone 1", bands, marks: [] }]} />)
    const lane = screen.getByRole("region", { name: "Lane: Phone 1" })
    const noData = lane.querySelector('[title="No data"]')!
    const withRecords = lane.querySelector('[title="No continuous recording; records this hour"]')!
    expect(withRecords.className).not.toEqual(noData.className)
    const swatch = (words: string) => screen.getByText(words).querySelector("[data-legend-swatch]")!
    expect(swatch("No continuous recording; records this hour").className).not.toEqual(swatch("No data").className)
  })

  it("is one component: defined once, used by the Timeline window, the Day view and the phone lens (03 T-1)", () => {
    const defining = Object.entries(sources).filter(([, src]) => /export function Lanes\(/.test(src)).map(([p]) => p)
    expect(defining).toEqual(["/src/features/pattern/components/Lanes.tsx"])
    const users = Object.entries(sources).filter(([, src]) => /<Lanes[\s>]/.test(src)).map(([p]) => p).sort()
    expect(users).toEqual([
      "/src/features/pattern/components/PatternsPage.tsx",
      "/src/features/pattern/components/WindowPanel.tsx",
      "/src/features/timeline/lens/PhoneLens.tsx",
    ])
    expect(sources["/src/features/timeline/components/TimelinePage.tsx"]).toContain("TimelineWindowBar")
  })
})
