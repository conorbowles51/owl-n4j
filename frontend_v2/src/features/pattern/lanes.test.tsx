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

  it("is one component: defined once, used by the Timeline window and the Day view", () => {
    const defining = Object.entries(sources).filter(([, src]) => /export function Lanes\(/.test(src)).map(([p]) => p)
    expect(defining).toEqual(["/src/features/pattern/components/Lanes.tsx"])
    const users = Object.entries(sources).filter(([, src]) => /<Lanes[\s>]/.test(src)).map(([p]) => p).sort()
    expect(users).toEqual(["/src/features/pattern/components/PatternsPage.tsx", "/src/features/pattern/components/WindowPanel.tsx"])
    expect(sources["/src/features/timeline/components/TimelinePage.tsx"]).toContain("TimelineWindowBar")
  })
})
