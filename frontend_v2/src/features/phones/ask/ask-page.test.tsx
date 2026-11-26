import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { askAPI, type Answer, type AskRow } from "./api"
import { AskPage } from "./AskPage"
import { corroborateStart, permissionLine } from "./ask-logic"
import { getSelection } from "@/features/corroborate/selection-store"
import { corroborateAPI } from "@/features/corroborate/api"

const phones = [
  { extraction_id: "p1", label: "Phone 1", owner: "Priya Halloran", allowed: null },
  { extraction_id: "p2", label: "Phone 2", owner: "Marisol Teague", allowed: null },
  { extraction_id: "p3", label: "Phone 3", owner: "Dorian Pell", allowed: false },
]
const answer: Answer = {
  question: "Did anyone talk about the refund checks?",
  phones, read: ["p1", "p2"], left_out: ["p3"],
  searched: "Searched 244 messages and 31 calls",
  statements: [
    { text: "Marisol Teague told Dorian “the checks are in the drawer”.", cites: ["r1", "r2"], people: ["Marisol Teague", "Dorian Pell"], date_from: "2024-03-12", date_to: "2024-03-12",
      cite_labels: [{ record: "r1", label: "Phone 2 · Message 12 Mar 2024 10:20 AM UTC", extraction_id: "p2" }, { record: "r2", label: "Phone 2 · Message 12 Mar 2024 10:21 AM UTC", extraction_id: "p2" }],
      elsewhere: { rows: [{ source: "Timeline", text: "No event on 12 Mar.", relation: "nothing_found" },
        ...[1, 2, 3].map((n) => ({ source: "Phone 3", text: `Copy ${n} on Phone 3.`, relation: "agrees", relation_label: "Agrees", reason: "same text, same minute" })), { source: "Financial", text: "Checks 2204 to 2206 arrive in the account ending 7302.", cite: "txn://t1", cite_label: "pell-2024-03.pdf p.1", relation: "agrees", reason: "same amounts" }], note: null } },
    { text: "Priya Halloran wrote “check 2209 goes out today”.", cites: ["r3"], people: ["Priya Halloran"], date_from: "2024-02-12", date_to: null,
      cite_labels: [{ record: "r3", label: "Phone 1 · Message 12 Feb 2024 3:30 PM UTC", extraction_id: "p1" }],
      elsewhere: { rows: null, note: "The rest of the case was not checked for this statement yet." } },
  ],
  not_found: [{ asked: "check numbers 2201 to 2203", text: "No message names checks 2201 to 2203." }],
  notes: ["Phone 3 was left out: its Outside services decision is “not allowed” (Case settings)."],
  steps: [{ n: 1, kind: "corroborate", title: "Test Marisol Teague and Dorian Pell around 2024-03-12", why: "Statement 1 puts them together in 2 records.", action: { label: "Corroborate", kind: "corroborate", statement: 0 } },
    { n: 2, kind: "not_found", title: "Look in the rest of the case", why: "The phones did not answer this.", action: { label: "Search the case", kind: "case_search", q: "refund checks" } }],
  label: "Written by AI from the records · not confirmed",
  records_used: [{ record: "r1", label: "Phone 2 · Message", extraction_id: "p2", cited: true }, { record: "r9", label: "Phone 1 · Call", extraction_id: "p1", cited: false }],
  model: "deepseek/x", error: null,
}
const done: AskRow = { id: "a1", question: answer.question, phones: [], status: "done", error: null, answer, asked_by_name: "Test", created_at: "2026-11-25T22:00:00Z", seconds: 50 }

function page(url: string) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[url]}>
    <Routes><Route path="/cases/:id/phones/ask" element={<AskPage />} /><Route path="/cases/:id/search" element={<p>case search page</p>} /></Routes>
  </MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); vi.restoreAllMocks() })

describe("Ask the phones", () => {
  it("names the phones read and the phones left out by their Outside services decision", () => {
    expect(permissionLine(phones)).toContain("Reads 2 phones in scope")
    expect(permissionLine(phones)).toContain("Left out: Phone 3")
    expect(permissionLine(phones.slice(0, 2))).toContain("Reads all 2 phones")
  })

  it("shows each statement with its phone citations, what the rest of the case says, not found, and next steps", async () => {
    vi.spyOn(askAPI, "read").mockResolvedValue(done)
    vi.spyOn(askAPI, "earlier").mockResolvedValue({ total: 1, shown: 1, offset: 0, next_offset: null, items: [{ id: "a1", question: answer.question, status: "done", asked_by_name: "Test", created_at: done.created_at, statements: 2 }] })
    page("/cases/c1/phones/ask?ask=a1")
    const first = await screen.findByRole("article", { name: "Statement 1" })
    expect(within(first).getByRole("link", { name: /Phone 2 · Message 12 Mar 2024 10:20 AM UTC/ }).getAttribute("href")).toBe("/cases/c1/records/r1")
    expect(within(first).getAllByText("Agrees")).toHaveLength(2) // the Financial row and the first of the Phone 3 group
    expect(within(first).getByRole("link", { name: "pell-2024-03.pdf p.1" })).toBeTruthy()
    // a message's copies on another phone are one group: the first shown, the rest counted and opened on request
    expect(within(first).getByText("Copy 1 on Phone 3.")).toBeTruthy()
    expect(within(first).queryByText("Copy 3 on Phone 3.")).toBeNull()
    fireEvent.click(within(first).getByRole("button", { name: "2 more like this (Phone 3, agrees)" }))
    expect(within(first).getByText("Copy 3 on Phone 3.")).toBeTruthy()
    // checks that found nothing are folded under one line that names them, and open on request
    expect(within(first).queryByText("No event on 12 Mar.")).toBeNull()
    fireEvent.click(within(first).getByRole("button", { name: "Nothing found in 1 check: Timeline" }))
    expect(within(first).getByText("No event on 12 Mar.")).toBeTruthy()
    const second = screen.getByRole("article", { name: "Statement 2" })
    expect(within(second).getByText(/not checked for this statement yet/)).toBeTruthy()
    expect(screen.getByText("Written by AI from the records · not confirmed")).toBeTruthy()
    expect(screen.getByRole("region", { name: "Not found" }).textContent).toContain("No message names checks 2201 to 2203.")
    expect(screen.getByText(/Phone 3 was left out/)).toBeTruthy()
    const steps = screen.getByRole("region", { name: "Next steps" })
    expect(within(steps).getAllByRole("listitem")).toHaveLength(2)
    // earlier questions are listed with their count
    expect(await screen.findByText(/Test.*2 statements/)).toBeTruthy()
    // every record it used, cited or not
    fireEvent.click(screen.getByRole("button", { name: "Show every record it used" }))
    expect(screen.getByText(/The answer read 2 records; 1 are cited below/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /Phone 1 · Call · not cited/ })).toBeTruthy()
    fireEvent.click(within(steps).getByRole("button", { name: "Search the case" }))
    expect(await screen.findByText("case search page")).toBeTruthy()
  })

  it("Corroborate this puts the statement's cited records in the selection with its period", async () => {
    vi.spyOn(askAPI, "read").mockResolvedValue(done)
    vi.spyOn(askAPI, "earlier").mockResolvedValue({ total: 0, shown: 0, offset: 0, next_offset: null, items: [] })
    vi.spyOn(corroborateAPI, "preview").mockReturnValue(new Promise(() => {}))
    page("/cases/c1/phones/ask?ask=a1")
    const first = await screen.findByRole("article", { name: "Statement 1" })
    fireEvent.click(within(first).getByRole("button", { name: "Corroborate this statement" }))
    const sel = getSelection("c1")
    expect(sel).toHaveLength(1)
    expect(sel[0].members.map((m) => m.id)).toEqual(["r1", "r2"])
    expect(sel[0].label).toContain("Marisol Teague")
    expect(corroborateStart(answer, 0).scope).toEqual({ from: "2024-03-12", to: "2024-03-12" })
    expect(corroborateStart(answer, "all").members.map((m) => m.id)).toEqual(["r1", "r2", "r3"])
    expect(corroborateStart(answer, "all").scope).toEqual({ from: "2024-02-12", to: "2024-03-12" })
  })

  it("asks with the phones in scope and opens the running question", async () => {
    const ask = vi.spyOn(askAPI, "ask").mockResolvedValue({ ...done, id: "a2", status: "running", answer: null })
    vi.spyOn(askAPI, "read").mockResolvedValue({ ...done, id: "a2", status: "running", answer: null })
    vi.spyOn(askAPI, "earlier").mockResolvedValue({ total: 0, shown: 0, offset: 0, next_offset: null, items: [] })
    page("/cases/c1/phones/ask?phones=p1,p2&q=Who%20moved%20the%20money%3F")
    expect((screen.getByLabelText("Ask the phones a question") as HTMLInputElement).value).toBe("Who moved the money?")
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith("c1", "Who moved the money?", ["p1", "p2"]))
    expect(await screen.findByRole("status")).toBeTruthy()
    expect(screen.getByText("No questions asked yet.")).toBeTruthy()
  })
})
