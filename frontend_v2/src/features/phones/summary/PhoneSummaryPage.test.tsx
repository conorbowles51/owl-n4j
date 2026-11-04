import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { Profile } from "../schemas"

/** Phone summary (03 section 7; 07 J-2, J-11, J-15) with the server stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({
  getProfile: vi.fn(), setOwner: vi.fn(), setPhoneLabel: vi.fn(), acceptReconciliationDifference: vi.fn(), getSinceLastLooked: vi.fn(), getExportHistory: vi.fn().mockResolvedValue({ items: [] }), createExport: vi.fn(), getExport: vi.fn(),
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
// the coverage panel reads the coverage summary (07 J-13 step 6), the same counts as the thread list
const share = vi.hoisted(() => ({
  getReviewCoverage: vi.fn().mockResolvedValue({
    counts: { threads: 3, reviewed: 1, partly_reviewed: 1, not_reviewed: 2, never_reviewed: 1 },
    words: "", cover: [], keyword_lists: [], terms: [], splits: [], second_pass: [], searches: [],
    reviewers: [{ name: "A Reviewer", reviewed: 1, partly_reviewed: 1, messages_at_review: 17 }],
    partly_reviewed: [{ thread_key: "t1", title: "Synthetic thread", phone: "C3", messages: 15, review: "Reviewed by A Reviewer on Tuesday, March 14 (12 messages); 3 added since", added_since: 3 }],
    not_reviewed: [{ thread_key: "t3", title: "Third", phone: "C3", messages: 1, review: null, added_since: null }],
    reviewed: [{ thread_key: "t2", title: "Other", phone: "C3", messages: 5, review: "Reviewed by A Reviewer on Tuesday, March 14 (5 messages)", added_since: 0 }],
  }),
}))
vi.mock("../review-share", async (orig) => ({ ...(await orig<object>()), ...share }))

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
    completeness: { reconciliation: "exact", state: "ingested", documents: [], held: [] },
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
    busiest_weeks: [{ week: "2023-01-02", last_day: "2023-01-08", events: 5, words: "Week of Monday, January 2, 2023", link: `${conv}?from=2023-01-02&to=2023-01-08&notime=0` }],
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

  it("a held difference offers See which, Accept the difference with a typed reason, and Keep held (07 J-1)", async () => {
    const held = [{ document_index: 0, document: "C2_Report.xml", difference_count: 2, shown: 2, accepted: null,
      differences: [{ where: "decodedData / modelType / model", measure: "elements", what: "elements", attribute: null, stated: 1204, read: 1198 },
        { where: "modelType / model / field", measure: "texts", what: "texts", attribute: null, stated: 9, read: 8 }] }]
    const words = "Held: the report lists 1,204 elements at decodedData / modelType / model; 1,198 were read. 1 more difference."
    api.getProfile.mockResolvedValue(profile({ completeness: { reconciliation: "failed", state: "ingested", documents: [], held }, needs: [{ kind: "reconciliation", words, link: null }] }))
    api.acceptReconciliationDifference.mockResolvedValue({ decision_id: "d3", differences: 2, restart: { state: "queued", words: "The difference is accepted. Reading continues from the check; the phone summary updates as it goes." } })
    page()
    const box = await screen.findByLabelText("Held by the check")
    expect(within(box).getByText(words, { exact: false })).toBeInTheDocument()
    fireEvent.click(within(box).getByRole("button", { name: "See which" }))
    expect(within(box).getByText("1,204")).toBeInTheDocument()
    expect(within(box).getByText("C2_Report.xml: 2 differences")).toBeInTheDocument()
    fireEvent.click(within(box).getByRole("button", { name: "Keep held" }))
    expect(within(box).getByText(/^Kept held\./)).toBeInTheDocument()
    expect(api.acceptReconciliationDifference).not.toHaveBeenCalled()
    fireEvent.click(within(box).getByRole("button", { name: "Change this" }))
    fireEvent.click(within(box).getByRole("button", { name: "Accept the difference" }))
    const form = within(box).getByRole("form", { name: "Accept the difference" })
    const save = within(form).getByRole("button", { name: "Accept the difference" })
    expect(save).toBeDisabled()
    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "synthetic reason" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.acceptReconciliationDifference).toHaveBeenCalledWith("case-1", "e1", "synthetic reason"))
    expect(await within(box).findByText(/^2 differences accepted\. The difference is accepted\./)).toBeInTheDocument()
  })

  it("busiest weeks link to their week, Since you last looked counts from the previous visit, and the export history and profile PDF are offered (03 7.3, J-15)", async () => {
    localStorage.setItem("loupe.phone.lastLooked.case-1.e1", "2023-01-01T00:00:00.000Z")
    api.getSinceLastLooked.mockResolvedValue({ since: "2023-01-01T00:00:00Z", counts: { new_phones: 1, this_phone_read_again: false }, lines: ["1 new phone", "0 phones replaced"], nothing: false })
    api.getExportHistory.mockResolvedValue({ items: [
      { export_id: "x1", format: "pdf", source: "stream", state: "done", progress: 1, counts: { total: 12 }, file: { filename: "a.pdf", size: 1, sha256: "s" }, error: null, created_at: "2023-01-03T00:00:00Z", finished_at: null, title: "Synthetic", phones: ["e1"] },
      { export_id: "x2", format: "pdf", source: "stream", state: "done", progress: 1, counts: { total: 3 }, file: null, error: null, created_at: null, finished_at: null, title: null, phones: ["other"] },
      // a finding exported as its frozen selection on another phone, and a whole-case stream export
      { export_id: "x4", format: "pdf", source: "finding", state: "done", progress: 1, counts: { total: 2 }, file: null, error: null, created_at: null, finished_at: null, title: "Finding", phones: ["other"], whole_case: false },
      { export_id: "x5", format: "pdf", source: "stream", state: "done", progress: 1, counts: { total: 9 }, file: null, error: null, created_at: null, finished_at: null, title: "Everything", phones: [], whole_case: true },
    ] })
    api.createExport.mockResolvedValue({ export_id: "x3" })
    api.getExport.mockResolvedValue({ export_id: "x3", format: "pdf", source: "phone_profile", state: "done", progress: 1, counts: {}, file: { filename: "phone-summary.pdf", size: 1, sha256: "s" }, error: null, created_at: null, finished_at: null })
    page()
    const weeks = await screen.findByRole("region", { name: "Busiest weeks" })
    expect(within(weeks).getByRole("link", { name: "Week of Monday, January 2, 2023: 5 messages and calls" })).toHaveAttribute("href", `${conv}?from=2023-01-02&to=2023-01-08&notime=0`)
    const since = screen.getByRole("region", { name: "Since you last looked" })
    expect(await within(since).findByText("1 new phone")).toBeInTheDocument()
    expect(api.getSinceLastLooked).toHaveBeenCalledWith("case-1", "e1", "2023-01-01T00:00:00.000Z")
    const hist = screen.getByRole("region", { name: "Export history" })
    expect(await within(hist).findByText("2 exports cover this phone.")).toBeInTheDocument()
    expect(within(hist).getByText(/"Everything" \(every phone in the case\)/)).toBeInTheDocument()
    expect(within(hist).queryByText(/"Finding"/)).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Export profile as PDF" }))
    await waitFor(() => expect(api.createExport).toHaveBeenCalledWith("case-1", { case_id: "case-1", phones: ["e1"] }, { title: "Phone summary: C2" }, "pdf", "phone_profile"))
    expect(await screen.findByRole("button", { name: "Download phone-summary.pdf" })).toBeInTheDocument()
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
