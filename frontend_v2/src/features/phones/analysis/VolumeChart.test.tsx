import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 14.4: the volume chart with changepoints, every count opening to its records. Invented data only. */
const volume = vi.hoisted(() => vi.fn())
vi.mock("./analysis-api", () => ({ relationshipVolume: volume }))
import { viewFromSearch, viewToFilter } from "../lib/filter-url"
import { VolumeChart } from "./VolumeChart"
import { changeWords, weekRecordsPath } from "./volume-words"

const V = {
  result_id: "r1", phone_label: "C1", extraction_id: "ext-1", identity_keys: ["phone:+12025550143"], total: 30, untimed: 2, changed_words: null,
  weeks: [{ week_start: "2023-01-02", count: 10 }, { week_start: "2023-01-09", count: 20 }, { week_start: "2023-01-16", count: 0 }, { week_start: "2023-01-23", count: 0 }],
  changepoints: [{ result_id: "c1", week_start: "2023-01-16", direction: "fall", rate_before: 15, rate_after: 0, weeks_before: 2, weeks_after: 2 }],
}
function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname}{l.search}</p>
}
function page() {
  volume.mockResolvedValue(V)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Routes><Route path="*" element={<><VolumeChart caseId="c1" resultId="r1" /><Where /></>} /></Routes></MemoryRouter>
    </QueryClientProvider>)
}

describe("the relationship volume chart", () => {
  it("draws every week, zeros included, and a rule on each changepoint with its words", async () => {
    page()
    const fig = await screen.findByTestId("volume-chart")
    expect(fig.querySelectorAll("[data-week]").length).toBe(4)
    expect(fig.querySelectorAll("[data-changepoint='2023-01-16']").length).toBe(1)
    expect(within(fig).getByRole("list", { name: "Weeks where contact changed" })).toHaveTextContent(changeWords(V.changepoints[0]))
    expect(changeWords({ direction: "rise", week_start: "2024-01-29", rate_before: 0, rate_after: 3.714 })).toContain("about 0 a week, then about 3.7 a week")
    expect(fig).toHaveTextContent("2 calls, messages and emails with no time are not on the chart.")
  })

  it("opens a bar to exactly that week, on that phone, in the zone it was counted in", async () => {
    page()
    const fig = await screen.findByTestId("volume-chart")
    fireEvent.click(fig.querySelector("[data-week='2023-01-09']")!)
    const url = new URL(screen.getByTestId("where").textContent!, "http://x")
    expect(url.pathname).toBe("/cases/c1/conversations")
    const q = url.searchParams
    expect([q.get("people"), q.get("phones"), q.get("from"), q.get("to"), q.get("zone"), q.get("copies"), q.get("kinds"), q.get("notime")])
      .toEqual(["phone:+12025550143", "ext-1", "2023-01-09", "2023-01-15", "utc", "all", "message,call,email", "0"])
  })

  it("a week and the total hold only records with a time, as the bars do", () => {
    expect(new URL(weekRecordsPath("c1", V), "http://x").searchParams.get("notime")).toBe("0")
  })

  it("the week's list is the week counted, in a case with another zone", () => {
    const view = viewFromSearch(new URL(weekRecordsPath("c1", V, "2023-01-09"), "http://x").search)
    const f = viewToFilter("c1", view, "America/New_York")
    expect([f.from_instant, f.to_instant]).toEqual(["2023-01-09T00:00:00.000Z", "2023-01-15T23:59:59.999Z"])
  })

  it("opens the total and each row of the table to records", async () => {
    page()
    const fig = await screen.findByTestId("volume-chart")
    expect(within(fig).getByRole("link", { name: "30 calls, messages and emails" }).getAttribute("href")).toBe(weekRecordsPath("c1", V))
    expect(within(fig).getByRole("link", { name: "20" }).getAttribute("href")).toBe(weekRecordsPath("c1", V, "2023-01-09"))
  })
})
