import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { Profile } from "../schemas"

/** Phone summary (03 section 7; 07 J-2, J-11, J-15) with the server stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({
  getProfile: vi.fn(), setOwner: vi.fn(), setPhoneLabel: vi.fn(),
  getThreads: vi.fn().mockResolvedValue({
    counts: { threads: 3, reviewed: 1, partly_reviewed: 1, not_reviewed: 2 },
    items: [
      { thread_key: "t1", title: "Synthetic thread", review: { by: "A Reviewer", at: "2023-03-14T00:00:00Z", record_count: 12, added_since: 3, words: "Reviewed by A Reviewer on Tuesday, March 14 (12 messages); 3 added since" } },
      { thread_key: "t2", title: "Other", review: { by: "A Reviewer", at: "2023-03-14T00:00:00Z", record_count: 5, added_since: 0, words: "Reviewed by A Reviewer on Tuesday, March 14 (5 messages)" } },
      { thread_key: "t3", title: "Third", review: null },
    ],
  }),
}))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import PhoneSummaryPage from "./PhoneSummaryPage"

const label = (name: string, owner = false) => ({ identity_key: `phone:${name}`, name, name_basis: "contact_on_this_phone" as const, identifier: null, is_owner: owner, owner_basis: null, case_names: [] })
const conv = "/cases/case-1/phones/e1/records/conversations"

function profile(over: Partial<Profile> = {}): Profile {
  return {
    phone: { extraction_id: "e1", label: "C2", owner: label("Owner", true), device: { manufacturer: "Synthetic", model: "S1", os: null }, state: "ingested", standing: "active", ingest_progress: null, device_zone: null, device_zone_basis: null, report_version: "7", form: "ufdr", report_filename: "C2.ufdr", ingested_at: null, counts: { messages: 600, calls: 6, emails: 0, locations: 0, files: 4, timeline_entries: 0 } } as unknown as Profile["phone"],
    verdict: { word: "Read in full", sentence: "Read in full: 659 records, Monday, January 2, 2023 to Friday, July 7, 2023, 3 apps. 2 things need a decision.", records: 659, apps: 3, first_day: "x", last_day: "y", needs_decision: 2 },
    owner: { label: null, basis: "unidentified", words: "No owner number was found.", missing: true, decided: false, keys: [], candidates: [{ identity_key: "phone:+12025550100", text: "+1 202-555-0100", tier: 2, occurrences: 3, basis: "sent" }] },
    zone: { device_zone: null, basis: null, case_zone: "Eastern time" },
    report: { filename: "C2.ufdr", form: "ufdr", report_version: "7", producer: null, extraction_type: null, container_name: null, container_sha256: null, report_sha256: null, extraction_start: null, ingested_at: null },
    selection: [{ flag: "IsSelectiveExtraction", name: "Selective extraction", verbatim: "not stated", meaning: null }],
    completeness: { reconciliation: "exact", state: "ingested", documents: [] },
    files: { total: 4, by_category: { Image: 4 }, verification: { match: 3, missing: 1 }, link: "/m" },
    deleted: { comm_events: 12, link: `${conv}?deleted=only`, by_type: [] },
    coverage: [{ model_type: "InstantMessage", records: 600, level: "reviewed", level_words: "Interpreted" }],
    data_periods: [{ signal: "messages", records: 600, dated: 594, first_words: "a", last_words: "b" }],
    months: [{ month: "2023-01", messages: 5, calls: 1, other: 0 }, { month: "2023-02", messages: 0, calls: 0, other: 0 }],
    apps: [{ app: "SyntheticApp", events: 6 }],
    top_people: [{ label: label("Synthetic A"), text: "Synthetic A (no identifier recorded)", events: 41, link: `${conv}?tab=people&people=phone:Synthetic A` }],
    needs: [
      { kind: "owner", words: "No owner number was found. Person-level views stay off until an owner is set. Set the owner.", link: "/cases/case-1/phone-review" },
      { kind: "zone", words: "This phone did not record its time zone. Times show in the case zone (Eastern time).", link: "/cases/case-1/settings" },
    ],
    where_to_start: [{ words: "Look at the 12 deleted messages and calls", link: `${conv}?deleted=only` }],
    zone_name: "America/New_York",
    links: { conversations: conv, review: "/cases/case-1/phone-review" },
    ...over,
  }
}

function page() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/cases/case-1/phones/e1"]}>
          <Routes>
            <Route path="/cases/:id/phones/:extraction" element={<PhoneSummaryPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe("Phone summary", () => {
  it("Set the owner saves the chosen number with the reason, and asks for both first (03 section 7.3)", async () => {
    api.setOwner.mockResolvedValue({ decision_id: "d1", owner_identity_keys: ["phone:+12025550100"] })
    page()
    const form = await screen.findByRole("form", { name: "Set the owner" })
    const save = within(form).getByRole("button", { name: "Save owner" })
    expect(save).toBeDisabled()
    fireEvent.change(within(form).getByRole("combobox"), { target: { value: "phone:+12025550100" } })
    expect(save).toBeDisabled()
    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "synthetic reason" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.setOwner).toHaveBeenCalledWith("case-1", "e1", "phone:+12025550100", "synthetic reason"))
    expect(await within(form).findByText(/^Owner set to \+1 202-555-0100\./)).toBeInTheDocument()
  })

  it("Name this phone saves the name with the reason, and asks for both first (02 section 12.3)", async () => {
    api.setPhoneLabel.mockResolvedValue({ decision_id: "d2", label: "C1", before: "Phone 1" })
    page()
    const form = await screen.findByRole("form", { name: "Name this phone" })
    const save = within(form).getByRole("button", { name: "Save name" })
    const [name, reason] = within(form).getAllByRole("textbox")
    fireEvent.change(name, { target: { value: " C1 " } })
    expect(save).toBeDisabled()
    fireEvent.change(reason, { target: { value: "synthetic reason" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.setPhoneLabel).toHaveBeenCalledWith("case-1", "e1", "C1", "synthetic reason"))
    expect(await within(form).findByText(/^This phone is now called C1\./)).toBeInTheDocument()
  })

  beforeEach(() => {
    localStorage.clear()
    api.getProfile.mockResolvedValue(profile())
  })

  it("the review coverage counts partly reviewed threads and says what was added since (07 J-13b)", async () => {
    page()
    const box = await screen.findByRole("region", { name: "Review coverage" })
    expect(await within(box).findByText("Not yet reviewed: 2 of 3 threads")).toBeInTheDocument()
    expect(within(box).getByText("Reviewed: 1. Partly reviewed: 1.")).toBeInTheDocument()
    expect(within(box).getByText(/\(12 messages\); 3 added since/)).toBeInTheDocument()
  })

  it("opens with the verdict, what needs a decision and the triage block (07 J-2)", async () => {
    page()
    expect(await screen.findByText(/^Read in full: 659 records, .+ to .+, 3 apps\./)).toBeInTheDocument()
    const box = screen.getByRole("region", { name: "Needs a decision" })
    expect(within(box).getByText(/No owner number was found\. Person-level views stay off until an owner is set\./)).toBeInTheDocument()
    expect(within(box).getByRole("button", { name: "Set the owner." })).toBeInTheDocument()
    expect(within(box).getByText(/This phone did not record its time zone\. Times show in the case zone/)).toBeInTheDocument()
    for (const name of ["Coverage by month", "Where to start"]) expect(screen.getByRole("heading", { name })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: /Top people/ })).toBeInTheDocument()
    expect(within(screen.getByRole("region", { name: "Top people" })).getByRole("link", { name: /41 messages and calls/ })).toHaveAttribute("href", `${conv}?tab=people&people=phone:Synthetic A`)
  })

  it("the header opens the phone's Media screen beside its Conversations", async () => {
    page()
    expect(await screen.findByRole("link", { name: "Media" })).toHaveAttribute("href", "/cases/case-1/phones/e1/records/media")
  })

  it("the deleted count opens the deleted messages (07 J-11) and a quiet month says none", async () => {
    page()
    expect(await screen.findByRole("link", { name: "12 deleted or in trash" })).toHaveAttribute("href", `${conv}?deleted=only`)
    expect(screen.getByText("none")).toBeInTheDocument()
  })

  it("the selection flags read verbatim, and not stated when absent (P-5)", async () => {
    page()
    expect(await screen.findByText("not stated")).toBeInTheDocument()
  })

  it("Continue reading lists the threads opened on this browser (07 J-15)", async () => {
    localStorage.setItem("loupe.continue-reading.case-1", JSON.stringify([{ thread: "t9", title: "Synthetic thread", phone: "C2", extraction: "e1", at: "2026-11-02T00:00:00Z" }]))
    page()
    const region = await screen.findByRole("region", { name: "Continue reading" })
    expect(within(region).getByRole("link", { name: "Synthetic thread" })).toHaveAttribute("href", `${conv}?thread=t9`)
  })
})
