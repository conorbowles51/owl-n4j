import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { StreamRow } from "../schemas"

const m = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<typeof import("@/lib/api-client")>()), fetchAPI: m.fetch }))
vi.mock("../collect-targets", () => ({ useCollectTargets: () => ({ targets: [], note: null, loading: false, error: null }) }))

import { ApiError } from "@/lib/api-client"
import { HomeRecordPanel } from "./HomeRecordPanel"
import { copyWithSource } from "./home-words"

const label = (name: string, owner = false) => ({ identity_key: `phone:${name}`, name, name_basis: "contact_on_this_phone", identifier: { kind: "phone", display: owner ? "+1 717-555-0211" : "+1 717-555-0261", subkind: null, captured: null, normalised: true }, is_owner: owner, owner_basis: null, phone_label: owner ? "Phone 1" : null, case_names: [] })
const ROW = {
  event_uid: "e1", record_uid: "r1", kind: "message", phone: { extraction_id: "p1", label: "Phone 1" }, app: "WhatsApp", thread: { thread_key: "t", title: null },
  direction: "incoming", time: { instant: "2024-01-05T03:22:00Z", row: "3:22 AM", full: "Fri 5 Jan 2024, 3:22 AM UTC", offset_present: true },
  from: label("Nell"), to: [label("Priya Halloran", true)], body: "half now, half on Friday", subject: null, call: null, attachments: [], flags: [],
  copies: { count: 1, record_uids: ["r1"], apps: [] }, owner_read: { date_read: null, date_played: null }, interpretation_level: "reviewed", line: "",
} as unknown as StreamRow

function show(alsoOn: string[] = []) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><HomeRecordPanel caseId="c1" row={ROW} phoneIndex={() => 0} alsoOn={alsoOn} onThatDay={() => undefined} /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => m.fetch.mockReset())

describe("the Phones page's record panel", () => {
  it("shows the words, who, when, the app and the source, and every action", async () => {
    m.fetch.mockResolvedValue({ parts: [] })
    show()
    const panel = screen.getByRole("complementary", { name: "Selected record" })
    expect(panel).toHaveTextContent("“half now, half on Friday”")
    expect(panel).toHaveTextContent("Nell")
    expect(panel).toHaveTextContent("Owner of Phone 1: Priya Halloran (+1 717-555-0211)")
    expect(panel).toHaveTextContent("Fri 5 Jan 2024, 3:22 AM UTC")
    expect(panel).toHaveTextContent("Phone 1 report, the message record")
    for (const name of ["Add to the case", "Read the thread", "That day, all phones", "Corroborate", "Copy with source"])
      expect(within(panel).getByRole(name === "Read the thread" ? "link" : "button", { name })).toBeInTheDocument()
    expect(within(panel).getByRole("link", { name: "Read the thread" })).toHaveAttribute("href", "/cases/c1/phones/p1/records/conversations?record=r1")
    expect(within(panel).getAllByRole("button", { name: "Corroborate" })).toHaveLength(1) // not twice (Add to's own)
  })

  it("Elsewhere in the case shows each part's relation, text and citation from the elsewhere service, one request per part", async () => {
    m.fetch.mockImplementation(async (url: string) => {
      const part = new URL(url, "http://x").searchParams.get("part")
      if (part === "financial") return { parts: [{ source: "financial", label: "Financial", state: "done", items: [{ relation: "possible_match", relation_label: "Possible match, not confirmed", text: "A $1,100 cash withdrawal on Fri 12 Jan.", reason: "Same person, next Friday.", citation: { kind: "transaction", id: "t9", label: "the withdrawal" } }] }] }
      return { parts: [{ source: part, label: part, state: "done", items: [{ relation: "nothing_found", relation_label: "Nothing found", text: `Nothing in ${part}.` }] }] }
    })
    show()
    const box = await screen.findByRole("region", { name: "Elsewhere in the case" })
    expect(await within(box).findByText(/A \$1,100 cash withdrawal/)).toBeInTheDocument()
    expect(within(box).getByRole("link", { name: "the withdrawal" })).toHaveAttribute("href", "/cases/c1/financial?transaction=t9")
    expect(m.fetch.mock.calls.map((c) => c[0])).toEqual(["phones", "financial", "documents", "timeline"].map((p) => `/api/cases/c1/elsewhere/record/r1?part=${p}`))
  })

  it("until the elsewhere service is on the server, it checks the other phones only and says so", async () => {
    m.fetch.mockImplementation(async (url?: string) => { if (String(url).includes("/elsewhere/")) throw new ApiError("Not Found", 404); return {} })
    show(["Phone 3"])
    const box = await screen.findByRole("region", { name: "Elsewhere in the case" })
    expect(await within(box).findByText(/Also on Phone 3\./)).toBeInTheDocument()
    expect(box).toHaveTextContent("Only the other phones were checked")
  })

  it("Copy with source keeps the words exactly and says where they come from", () => {
    expect(copyWithSource(ROW, "http://h/cases/c1/records/r1")).toBe(
      "\"half now, half on Friday\"\nFrom Nell (+1 717-555-0261). To Owner of Phone 1: Priya Halloran (+1 717-555-0211). Fri 5 Jan 2024, 3:22 AM UTC. WhatsApp. Phone 1 report, record r1\nhttp://h/cases/c1/records/r1")
  })
})
