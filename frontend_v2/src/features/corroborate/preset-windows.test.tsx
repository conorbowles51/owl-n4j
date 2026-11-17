import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { corroborateAPI, type Incident } from "./api"
import { IncidentPresets } from "./IncidentPresets"
import { presetScope } from "./preset-windows"

const dated: Incident = { date: "2026-05-03", time: "21:30", words: "2026-05-03 21:30", entry_id: "e1", entry_type: "theory", title: "Night of the 3rd" }
const dayOnly: Incident = { ...dated, time: null, words: "3 May 2026", entry_id: "e2" }

beforeEach(() => vi.restoreAllMocks())

describe("Preset windows from incident dates", () => {
  it("builds hours from a stated time, whole days and weeks from a date, and never guesses an hour", () => {
    expect(presetScope(dated, "hour")).toMatchObject({ zone: "UTC", window: { from_at: "2026-05-03T20:30:00.000Z", to_at: "2026-05-03T22:30:00.000Z" } })
    expect(presetScope(dayOnly, "hour")).toBeNull()
    expect(presetScope(dayOnly, "day")).toEqual({ zone: "UTC", from: "2026-05-02", to: "2026-05-04" })
    expect(presetScope(dayOnly, "week")).toEqual({ zone: "UTC", from: "2026-04-26", to: "2026-05-10" })
  })
  it("lists each date with its words, turns the hour button off without a time, and hands the scope on", async () => {
    vi.spyOn(corroborateAPI, "incidents").mockResolvedValue({ incidents: [dated, dayOnly] })
    const picked = vi.fn()
    render(<QueryClientProvider client={new QueryClient()}><IncidentPresets caseId="c1" onPick={picked} /></QueryClientProvider>)
    await screen.findByText(/from "3 May 2026"/)
    const hours = screen.getAllByRole("button", { name: "± 1 hour" })
    expect((hours[1] as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getAllByRole("button", { name: "± 1 day" })[0])
    expect(picked).toHaveBeenCalledWith({ zone: "UTC", from: "2026-05-02", to: "2026-05-04" })
  })
})
