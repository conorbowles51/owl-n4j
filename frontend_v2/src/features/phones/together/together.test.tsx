import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { TogetherPanel } from "./TogetherPanel"
import { TogetherBand } from "./TogetherBand"
import { phoneTogetherEnabled } from "./enabled"
import { meetingWhen, type Overlaps } from "./phone-together"

vi.mock("@/features/relations/LookInto", () => ({ LookInto: ({ items }: { items: unknown[] }) => <button type="button">Corroborate {items.length}</button> }))

const base: Overlaps = {
  case_id: "c", phones: [{ id: "a", label: "Phone 2" }, { id: "b", label: "Phone 3" }], together: [], cells: 0,
  shared_contacts: [], relay_chains: [], pairs: [], message: "No meeting found in 8 timed positions of these phones (same 15-minute slot and same 550 m square, the whole period of the case).",
  contacts_message: "No person has records on two or more of these phones in the whole period of the case.",
  relay_message: "No relay chain found in 7 contacts of these phones in the whole period of the case.", searched: ["Positions: 8"], out_of_reach: ["2 positions have no time and cannot be placed with the other phone."],
}
const meeting = {
  id: "m1", phones: ["a", "b"], start: "2024-05-24T00:30:00+00:00", end: "2024-05-24T02:45:00+00:00", cells: 3, readings: 6, days: ["2024-05-24"],
  place: { lat: 39.26, lon: -76.67, square_m: 550 }, precision: { best_accuracy_m: 6, accuracy_stated: true, sources: ["device_location"], level: "fine" },
  records: { a: ["r1", "r2"], b: ["r3"] }, records_total: { a: 2, b: 1 },
  busy: { other_phones: 3, phones_total: 6, is_busy: true, words: "3 other phones of the 6 in the case also have positions in this 550 m square in the period, so being here at one time is weak evidence of meeting." },
}

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)

beforeEach(() => localStorage.clear())

describe("phoneTogetherEnabled", () => {
  it("is off until switched on, and stays on for this browser", () => {
    expect(phoneTogetherEnabled()).toBe(false)
    window.history.pushState({}, "", "/?phone_together=on")
    expect(phoneTogetherEnabled()).toBe(true)
    window.history.pushState({}, "", "/")
    expect(phoneTogetherEnabled()).toBe(true)
    window.history.pushState({}, "", "/?phone_together=off")
    expect(phoneTogetherEnabled()).toBe(false)
    window.history.pushState({}, "", "/")
  })
})

describe("TogetherPanel", () => {
  it("with no meeting reads what was searched, never blank", () => {
    wrap(<TogetherPanel caseId="c" phoneIds={["a", "b"]} parts={["places", "contacts", "relay"]} data={base} />)
    expect(screen.getByText(/^No meeting found in 8 timed positions/)).toBeTruthy()
    expect(screen.getByText(/^No person has records on two or more/)).toBeTruthy()
    expect(screen.getByText(/^No relay chain found in 7 contacts/)).toBeTruthy()
    expect(screen.getByText(/Out of reach: 2 positions have no time/)).toBeTruthy()
  })
  it("a meeting says when, how precise, how busy, opens its records and offers Corroborate with all of them", () => {
    wrap(<TogetherPanel caseId="c" phoneIds={["a", "b"]} parts={["places"]} data={{ ...base, together: [meeting] }} />)
    expect(screen.getByText(/3 time slots of 15 minutes in the same 550 m square, best accuracy 6 m/)).toBeTruthy()
    expect(screen.getByText("Busy place: weak")).toBeTruthy()
    expect(screen.getByText("Open the 3 records")).toBeTruthy()
    expect(screen.getByText("Corroborate 3")).toBeTruthy()
  })
  it("states when fewer than two or more than eight phones are on", () => {
    wrap(<TogetherPanel caseId="c" phoneIds={["a"]} parts={["places"]} />)
    expect(screen.getByText(/at least two phones/)).toBeTruthy()
    wrap(<TogetherPanel caseId="c" phoneIds={Array.from({ length: 9 }, (_, i) => `p${i}`)} parts={["places"]} />)
    expect(screen.getByText(/9 phones are on/)).toBeTruthy()
  })
})

describe("TogetherBand", () => {
  it("says what was searched when the two phones never met", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(base), { status: 200, headers: { "content-type": "application/json" } }))
    wrap(<TogetherBand caseId="c" phoneIds={["a", "b"]} />)
    await waitFor(() => expect(screen.getByText(/Shared moments: No meeting found in 8 timed positions/)).toBeTruthy())
  })
})

describe("meetingWhen", () => {
  it("writes one evening as a date and a span in UTC", () => {
    expect(meetingWhen(meeting)).toBe("24 May 2024, 00:30 to 02:45 UTC")
  })
})
