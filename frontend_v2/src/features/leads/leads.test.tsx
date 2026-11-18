import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { setSwitch } from "@/lib/ui-switches"
import { getSelection } from "@/features/corroborate/selection-store"
import { corroborateAPI } from "@/features/corroborate/api"
import { leadsAPI, searchedWords, type Lead } from "./api"
import { LeadsPage } from "./LeadsPage"
import { CorroboratePanel } from "./CorroboratePanel"
import { openCorroborate, clearPendingCorroborate } from "./open"
import { clearLeadRecords, getShownLead, isShownRef } from "./highlight-store"

vi.mock("@/features/phones/collect-targets", () => ({ useCollectTargets: () => ({ targets: [{ kind: "theory", id: "t1", label: "Kell runs the crew" }], note: null, loading: false, error: null }) }))

function lead(over: Partial<Lead>): Lead {
  return {
    id: "l1", origin: "found_by_loupe", origin_words: "Found by Loupe", state: "new", state_words: "New", state_history: [],
    level: { key: "strong", name: "Strong" }, title: "Kell and Okafor through the prepaid phone", summary: "On 5 nights.",
    read: { title: "", summary: "", by: "Loupe's lead finder", words: "Read by Loupe's lead finder · not confirmed" },
    corrections: [], people: [{ key: "person:k", label: "Kell" }], period: { from: "2024-05-01", to: "2024-06-01" },
    kinds: ["contact"], kind_words: ["contact"], record_refs: ["phone_record:a", "phone_record:b"], raises: ["5 of 6 nights"], lowers: [],
    searched: {}, detail: {}, selection_id: "s1", run_id: null, unseen: true, watching: true, finding_id: null, confirmed: null,
    created_at: null, checked_at: null, ...over,
  }
}

const LEADS: Lead[] = [
  lead({ id: "a" }),
  lead({ id: "b", title: "Marsh and Okafor at the warehouse", kinds: ["together"], level: { key: "probable", name: "Probable" } }),
  lead({ id: "c", title: "Quillan's, once", kinds: ["together"], level: { key: "coincidence", name: "Coincidence likely" } }),
  lead({ id: "d", title: "Mateo Ruiz: no link found", level: { key: "no_link_found", name: "No link found" }, summary: "Nothing links Mateo Ruiz to the pattern.", searched: { records_read: { message: 683, position: 694 }, instances: 6 } }),
  lead({ id: "e", title: "let me check", level: { key: "set_aside", name: "Set aside" }, summary: "“let me check and come back to you” is on 6 phones (26 copies): a stock phrase." }),
]

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/cases/c1/leads"]}>
    <Routes><Route path="/cases/:id/leads" element={ui} /></Routes></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); setSwitch("corroborate-v2", true); clearPendingCorroborate(); clearLeadRecords() })

describe("the Leads page", () => {
  it("lists strongest first, folds coincidence with its count, says what was searched, and lists what was set aside", async () => {
    vi.spyOn(leadsAPI, "list").mockResolvedValue({ leads: LEADS, total: 5, finder: { status: "done", finished_at: "2026-11-18T10:00:00Z" } })
    wrap(<LeadsPage />)
    await screen.findByText("Kell and Okafor through the prepaid phone")
    const main = screen.getByRole("region", { name: "Leads, strongest first" })
    expect(main.textContent!.indexOf("Kell and Okafor")).toBeLessThan(main.textContent!.indexOf("Marsh and Okafor"))
    expect(screen.queryByText("Quillan's, once")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: /Coincidence likely \(1\)/ }))
    expect(screen.getByText("Quillan's, once")).toBeTruthy()
    expect(screen.getByText("Searched: 683 messages, 694 phone positions; 6 nights and days compared")).toBeTruthy()
    expect(screen.getByText(/a stock phrase/)).toBeTruthy()
  })

  it("filters by kind, and a filter never hides the coincidence count", async () => {
    vi.spyOn(leadsAPI, "list").mockResolvedValue({ leads: LEADS, total: 5, finder: { status: "done" } })
    wrap(<LeadsPage />)
    await screen.findByText("Kell and Okafor through the prepaid phone")
    fireEvent.click(screen.getByRole("button", { name: "Together 2" }))
    expect(screen.queryByText("Kell and Okafor through the prepaid phone")).toBeNull()
    expect(screen.getByText("Marsh and Okafor at the warehouse")).toBeTruthy()
    expect(screen.getByRole("button", { name: /Coincidence likely \(1\)/ })).toBeTruthy()
  })

  it("says when new material arrived since the last look, and the button starts a look", async () => {
    vi.spyOn(leadsAPI, "list").mockResolvedValue({ leads: [], total: 0, finder: { status: "done", new_material: true } })
    const find = vi.spyOn(leadsAPI, "find").mockResolvedValue({ status: "queued" })
    wrap(<LeadsPage />)
    expect(await screen.findByText(/New material has arrived since Loupe last looked/)).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Look for leads now" }))
    await waitFor(() => expect(find).toHaveBeenCalledWith("c1"))
  })

  it("shows Loupe's words beside a person's correction", async () => {
    vi.spyOn(leadsAPI, "list").mockResolvedValue({ leads: [lead({ title: "Kell's relay", read: { title: "Kell and Okafor through the prepaid phone", summary: "", by: "Loupe's lead finder", words: "Read by Loupe's lead finder · not confirmed" }, corrections: [{ field: "title", original: "Kell and Okafor through the prepaid phone", value: "Kell's relay", by_name: "Neil", at: "" }] })], total: 1, finder: { status: "done" } })
    wrap(<LeadsPage />)
    expect(await screen.findByText("Kell's relay")).toBeTruthy()
    expect(screen.getByText(/Loupe read:/)).toBeTruthy()
    expect(screen.getByText(/Read by Loupe's lead finder · not confirmed/)).toBeTruthy()
  })
})

describe("Corroborate from anywhere", () => {
  it("opens over the page with the leads already here, filtered to the chosen records, and joins the selection", async () => {
    const list = vi.spyOn(leadsAPI, "here").mockResolvedValue({ leads: [LEADS[0]], total: 1, finder: { status: "done" } })
    wrap(<><p>page under</p><CorroboratePanel /></>)
    act(() => openCorroborate({ caseId: "c1", screen: "Conversations", label: "1 message", members: [{ type: "phone_record", id: "a" }] }))
    expect(await screen.findByRole("dialog", { name: "Corroborate" })).toBeTruthy()
    expect(screen.getByText("page under")).toBeTruthy()
    expect(await screen.findByRole("tab", { name: "Leads already here 1" })).toBeTruthy()
    expect(list).toHaveBeenCalledWith("c1", expect.objectContaining({ records: ["phone_record:a"] }))
    expect(getSelection("c1")).toHaveLength(1)
    fireEvent.click(screen.getByRole("tab", { name: "Ask a new question" }))
    expect(screen.getByRole("button", { name: /Choose the question yourself/ })).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Close" }))
    expect(screen.queryByRole("dialog", { name: "Corroborate" })).toBeNull()
  })

  it("asks the question on the chosen records and the answer is saved to Leads as Asked by you", async () => {
    vi.spyOn(leadsAPI, "here").mockResolvedValue({ leads: [], total: 0, finder: { status: "done" } })
    vi.spyOn(corroborateAPI, "preview").mockResolvedValue({ questions: [{ kind: "in_contact", text: "Were Kell and Okafor in contact?", count: 2, count_words: "2 people", chips: {} }] } as never)
    const run = vi.spyOn(corroborateAPI, "run").mockResolvedValue({ group: { id: "g9", member_count: 1, left_out: 0 } })
    wrap(<CorroboratePanel />)
    act(() => openCorroborate({ caseId: "c1", screen: "the map", label: "1 position", members: [{ type: "phone_record", id: "p" }] }))
    fireEvent.click(await screen.findByRole("tab", { name: /Ask a new question/ }))
    fireEvent.click(await screen.findByRole("button", { name: /Were Kell and Okafor in contact\?/ }))
    await waitFor(() => expect(run).toHaveBeenCalledWith("c1", expect.objectContaining({ members: [{ type: "phone_record", id: "p" }] })))
  })

  it("a lead's Corroborate does not fill the case-wide selection", () => {
    openCorroborate({ caseId: "c1", screen: "Leads", label: "x", members: [{ type: "phone_record", id: "a" }] }, { keep: false })
    expect(getSelection("c1")).toEqual([])
  })
})

describe("Show these records", () => {
  it("marks the lead's records on every screen until the lead is closed", async () => {
    vi.spyOn(leadsAPI, "list").mockResolvedValue({ leads: [LEADS[0]], total: 1, finder: { status: "done" } })
    wrap(<><LeadsPage /><CorroboratePanel /></>)
    fireEvent.click((await screen.findAllByRole("button", { name: "Show these records" }))[0])
    expect(getShownLead()?.leadId).toBe("a")
    expect(isShownRef(getShownLead(), "phone_record:b")).toBe(true)
    expect(isShownRef(getShownLead(), "phone_record:z")).toBe(false)
    expect(screen.getByText(/Showing 2 records of the lead/)).toBeTruthy()
    // the bar opens the lead's days, so the marked records are on screen
    expect(screen.getByRole("link", { name: "Conversations" }).getAttribute("href")).toBe("/cases/c1/conversations?from=2024-05-01&to=2024-06-01")
    expect(screen.getByRole("link", { name: "Map" }).getAttribute("href")).toBe("/cases/c1/map?from=2024-05-01&to=2024-06-01")
    fireEvent.click(screen.getAllByRole("button", { name: "Close" }).at(-1)!)
    expect(getShownLead()).toBeNull()
  })
})

describe("searched words", () => {
  it("names photo places as photo places, never as positions", () => {
    expect(searchedWords({ records_read: { media_position: 5, position: 1 } })).toBe("5 photo places, 1 phone position")
  })
})
