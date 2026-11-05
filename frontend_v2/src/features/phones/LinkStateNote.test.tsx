import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 07 section 6.3, CO-8, CO-15: what happened to a linked record since it was collected. Invented data only. */
const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

import { LinkStateNote } from "./LinkStateNote"
import { useLinkChoice, useLinkStates, type LinkState } from "./link-states"

const NONE = { count: 0, records: 0, items: [], clipped: false }
const STATE: LinkState = {
  link_id: "l1", link_kind: "entry", target_type: "phone_record", target_id: "r1", states: [], records: 1,
  corrected: NONE, reading_changed: NONE, set_aside: null, reread: null, replaced: null, added_by: "Sam Example",
  through_seq: 0, needs_choice: false, can_choose: false, can_remove: true, kept: null,
}
const CHANGED = {
  count: 1, records: 1, clipped: false,
  items: [{ record_uid: "r1", field: "sender", was: "Ana", now: "Ben", by: "Sam Example", at: "2026-11-04T10:00:00+00:00",
            words: "Sender was Ana, now Ben, by Sam Example on 4 November 2026." }],
}

function Harness() {
  const states = useLinkStates("c1", "entry", "e1", true)
  const choice = useLinkChoice("c1", "entry", "e1")
  return <LinkStateNote caseId="c1" state={states.l1} busy={choice.isPending} onChoose={(state, c) => choice.mutateAsync({ state, choice: c, expectedVersion: 3 })} />
}

const wrap = (ui: React.ReactNode) => render(
  <MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider></MemoryRouter>)

describe("The state of a phone link", () => {
  it("shows nothing for an active link", () => {
    wrap(<LinkStateNote caseId="c1" state={STATE} />)
    expect(screen.getByTestId("link-state-note").textContent).toBe("")
  })

  it("shows both values of a corrected record (CO-8)", () => {
    const words = "Body: as collected old words, now new words, corrected by Sam Example on 4 November 2026."
    wrap(<LinkStateNote caseId="c1" state={{ ...STATE, states: ["corrected"], corrected: { ...CHANGED, items: [{ ...CHANGED.items[0], words }] } }} />)
    expect(screen.getByText("Corrected since collected")).toBeInTheDocument()
    expect(screen.getByText(words)).toBeInTheDocument()
  })

  it("says who changed a reading and when, and offers no Keep to someone else (CO-15)", () => {
    wrap(<LinkStateNote caseId="c1" state={{ ...STATE, states: ["reading_changed"], reading_changed: CHANGED, needs_choice: true }} onChoose={vi.fn()} />)
    expect(screen.getByText(CHANGED.items[0].words)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Keep" })).toBeNull()
    expect(screen.getByText("Keep or Remove is for Sam Example, who added this link.")).toBeInTheDocument()
  })

  it("tells the reader when a long list is clipped, with the true count", () => {
    wrap(<LinkStateNote caseId="c1" state={{ ...STATE, records: 12345, reading_changed: { ...CHANGED, count: 3000, records: 3000, clipped: true } }} />)
    expect(screen.getByText("Reading changed since collected (3,000 of 12,345 records)")).toBeInTheDocument()
    expect(screen.getByText("The first 1 of 3,000 changes are listed here; the export lists all of them.")).toBeInTheDocument()
  })

  it("sends Keep with the change it was made on, one request for the whole finding", async () => {
    const state = { ...STATE, states: ["reading_changed"], reading_changed: CHANGED, needs_choice: true, can_choose: true, through_seq: 7 }
    fetchAPI.mockReset().mockImplementation(async (url: string) => url.endsWith("/states") ? { links: { l1: state } } : { choice: "keep", removed: false })
    wrap(<Harness />)
    await userEvent.click(await screen.findByRole("button", { name: "Keep" }))
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith("/api/phones/links/l1/choice", {
      method: "POST", body: { case_id: "c1", link_kind: "entry", choice: "keep", through_seq: 7, expected_version: 3 } }))
    expect(fetchAPI.mock.calls.filter(([u]) => u === "/api/phones/links/states").length).toBeGreaterThanOrEqual(1)
  })

  it("shows the refusal when a choice is not saved, and hides Remove on an assessment's link", async () => {
    const state: LinkState = { ...STATE, states: ["reading_changed"], reading_changed: CHANGED, needs_choice: true, can_choose: true, can_remove: false }
    const onChoose = vi.fn().mockRejectedValue(new Error("The reading changed again while you were looking."))
    wrap(<LinkStateNote caseId="c1" state={state} onChoose={onChoose} />)
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull()
    await userEvent.click(screen.getByRole("button", { name: "Keep" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("The reading changed again")
  })
})
