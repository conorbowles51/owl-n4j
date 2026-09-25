import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import "@/styles/globals.css"
import { page } from "vitest/browser"
import { MemoryRouter } from "react-router-dom"
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import {
  duplicateCandidates,
  duplicateContextCandidates,
} from "@/test/duplicate-fixture"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"

import { FinancialAccessContext } from "../hooks/use-financial-access"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
it("opens candidate and coverage details in Chromium without making a write request", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url, options) => {
      expect(String(url)).toBe("/api/financial/duplicates?case_id=case-1")
      expect(options?.method ?? "GET").toBe("GET")
      return new Response(JSON.stringify(duplicateCandidates()))
    })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DuplicateCandidatesPanel caseId="case-1" />
    </QueryClientProvider>
  )
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  fireEvent.click(await screen.findByText(/Candidate group 1/))
  expect(screen.getByText("copy.ofx")).toBeVisible()
  expect(screen.getByText("Excluded from Transactions")).toBeVisible()
  fireEvent.click(screen.getByText("Documents not compared (1)"))
  expect(screen.getByText(/empty.pdf:/)).toBeVisible()
})

for (const width of [1280, 390]) {
  it(`keeps repeated-name, zero-row and exact-period source context through return at ${width}px`, async () => {
    await page.viewport(width, 900)
    const data = duplicateContextCandidates()
    const selected = data.groups[11].members[1]
    const period = selected.statement_context[1]
    const reads: string[] = []
    const nativeFetch = window.fetch.bind(window)
    vi.spyOn(window, "fetch").mockImplementation(async (url, options) => {
      const path = String(url)
      if (!path.startsWith("/api/")) return nativeFetch(url, options)
      expect(options?.method || "GET").toBe("GET")
      reads.push(path)
      if (path === "/api/financial/duplicates?case_id=case-1")
        return new Response(JSON.stringify(data))
      if (
        path ===
        `/api/financial/statement-periods/${period.period_id}/source?case_id=case-1`
      )
        return new Response(
          JSON.stringify({
            case_id: "case-1",
            period_id: period.period_id,
            source_document_id: selected.document_id,
            evidence_file_id: selected.evidence_file_id,
            filename: selected.filename,
            statement_id: selected.statement_id,
            recorded_digest_matches: true,
            file_bytes_verified: false,
            limitation:
              "Saved original file reference; file bytes not rechecked.",
            can_edit_import_details: true,
            reviewed_controls: {
              finalization_id: null,
              currency: "USD",
              balance_convention: "asset_balance",
              reason: "Saved from the printed statement",
              scope: "February 2026",
              controls: [
                {
                  role: "opening",
                  original_text: "Opening 50.00",
                  reviewed_value: "5000",
                  locator: { kind: "page_only", page: 7 },
                },
              ],
            },
          })
        )
      if (path === `/api/evidence/${selected.evidence_file_id}/file`)
        return new Response(
          "Synthetic original: January and February statement periods; February has no movements."
        )
      throw Error(`Unexpected request ${path}`)
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const view = render(
      <QueryClientProvider client={client}>
        <FinancialAccessContext.Provider
          value={{ canEdit: true, canUpload: false, ready: true, error: false }}
        >
          <MemoryRouter>
            <main className="p-4">
              <DuplicateCandidatesPanel caseId="case-1" showCrossCase={false} />
            </main>
          </MemoryRouter>
        </FinancialAccessContext.Provider>
      </QueryClientProvider>
    )
    await act(async () => {
      await page
        .getByRole("button", { name: "Compare documents", exact: true })
        .click()
    })
    await screen.findByText(/Candidate group 1 ·/)
    const summary = screen.getByText(/Candidate group 1 ·/)
    expect(summary).toHaveTextContent(
      "Example Bank · Synthetic company 1 · Account 00120000 · USD · 2026-01-01 to 2026-01-31"
    )
    expect(summary).toHaveTextContent("6 stored rows across 2 copies")
    await act(async () => {
      await page
        .getByRole("button", { name: "Next reading groups", exact: true })
        .click()
    })
    expect(screen.getByText("Reading groups 11–12 of 12")).toBeVisible()
    const groupSummary = screen.getByText(/Candidate group 12 ·/)
    await act(async () => {
      groupSummary.click()
    })
    const group = groupSummary.closest("details")!
    expect(
      within(group).getByText("Saved statement · no transactions")
    ).toBeVisible()
    const copy = within(group).getByRole("listitem", {
      name: "Copy 2: Monthly statements.txt",
    })
    expect(within(copy).getByText("0 stored rows")).toBeVisible()
    const trigger = within(copy).getByRole("button", {
      name: "Inspect statement source · 2026-02-01 to 2026-02-28 · USD",
    })
    trigger.scrollIntoView({ block: "center" })
    const before = window.scrollY
    await act(async () => {
      trigger.click()
    })
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent(
      "Monthly statements.txt · Example Bank · Synthetic company 12 · Account 00120011 · USD · 2026-02-01 to 2026-02-28"
    )
    expect(
      await within(dialog).findByRole("button", {
        name: "Inspect opening: 50.00 USD",
      })
    ).toBeVisible()
    expect(
      within(dialog).queryByRole("button", { name: /Edit account/ })
    ).toBeNull()
    expect(reads.some((path) => path.includes("/ledger/"))).toBe(false)
    await page.screenshot({
      element: dialog,
      path: `/tmp/loupe-duplicate-context-${width}-source.png`,
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Open statement file", exact: true })
        .click()
    })
    await expect
      .element(page.getByRole("dialog"))
      .toHaveTextContent(
        "Synthetic original: January and February statement periods; February has no movements."
      )
    await act(async () => {
      await page
        .getByRole("button", { name: "Close document", exact: true })
        .click()
    })
    await act(async () => {
      await page
        .getByRole("button", {
          name: "Back to candidate group 12",
          exact: true,
        })
        .click()
    })
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(group).toHaveAttribute("open")
    expect(screen.getByText("Reading groups 11–12 of 12")).toBeVisible()
    expect(Math.abs(window.scrollY - before)).toBeLessThan(50)
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      element: group,
      path: `/tmp/loupe-duplicate-context-${width}-returned.png`,
    })
    expect(reads).toContain(
      `/api/financial/statement-periods/${period.period_id}/source?case_id=case-1`
    )
    expect(reads).toContain(`/api/evidence/${selected.evidence_file_id}/file`)
    view.unmount()
    client.clear()
  })
}

it("opens an exact whole-file fallback without inventing a statement period, then returns to the copy", async () => {
  await page.viewport(1280, 900)
  const data = duplicateContextCandidates(1)
  const selected = data.groups[0].members[1]
  selected.statement_context = []
  const paths: string[] = []
  const nativeFetch = window.fetch.bind(window)
  vi.spyOn(window, "fetch").mockImplementation(async (url, options) => {
    const path = String(url)
    if (!path.startsWith("/api/")) return nativeFetch(url, options)
    expect(options?.method || "GET").toBe("GET")
    paths.push(path)
    if (path === "/api/financial/duplicates?case_id=case-1")
      return new Response(JSON.stringify(data))
    if (path === `/api/evidence/${selected.evidence_file_id}/file`)
      return new Response("Synthetic source with no saved statement period.")
    throw Error(`Unexpected request ${path}`)
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DuplicateCandidatesPanel caseId="case-1" showCrossCase={false} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  await act(async () => {
    await page
      .getByRole("button", { name: "Compare documents", exact: true })
      .click()
  })
  const summary = await screen.findByText(/Candidate group 1 ·/)
  await act(async () => {
    summary.click()
  })
  const copy = within(summary.closest("details")!).getByRole("listitem", {
    name: "Copy 2: Monthly statements.txt",
  })
  expect(copy).toHaveTextContent(
    "Saved statement account and period details are unavailable."
  )
  expect(
    within(copy).queryByRole("button", { name: /Inspect statement source/ })
  ).toBeNull()
  const trigger = within(copy).getByRole("button", {
    name: "Open original file",
  })
  await act(async () => {
    trigger.click()
  })
  await expect
    .element(page.getByRole("dialog"))
    .toHaveTextContent("Synthetic source with no saved statement period.")
  await act(async () => {
    await page
      .getByRole("button", { name: "Close document", exact: true })
      .click()
  })
  await waitFor(() => expect(trigger).toHaveFocus())
  expect(summary.closest("details")).toHaveAttribute("open")
  expect(
    paths.some(
      (path) =>
        path.includes("/statement-periods/") || path.includes("/ledger/")
    )
  ).toBe(false)
  view.unmount()
  client.clear()
})

for (const action of ["exclude", "restore"] as const) {
  it(`reveals ${action} confirmation with repeated-name statement context and returns without recording a decision`, async () => {
    await page.viewport(1280, 900)
    const data = duplicateContextCandidates()
    const selected = data.groups[11].members[1]
    if (action === "exclude") {
      selected.status = "admitted"
      selected.superseded_by_id = null
    } else data.excluded_documents = [selected]
    const requests = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url, options) => {
        expect(String(url)).toBe("/api/financial/duplicates?case_id=case-1")
        expect(options?.method || "GET").toBe("GET")
        return new Response(JSON.stringify(data))
      })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const view = render(
      <QueryClientProvider client={client}>
        <FinancialAccessContext.Provider
          value={{ canEdit: true, canUpload: false, ready: true, error: false }}
        >
          <main className="p-4">
            <DuplicateCandidatesPanel caseId="case-1" showCrossCase={false} />
          </main>
        </FinancialAccessContext.Provider>
      </QueryClientProvider>
    )
    await act(async () => {
      await page
        .getByRole("button", { name: "Compare documents", exact: true })
        .click()
    })
    await screen.findByText(/Candidate group 1 ·/)
    await act(async () => {
      await page
        .getByRole("button", { name: "Next reading groups", exact: true })
        .click()
    })
    const summary =
      action === "exclude"
        ? screen.getByText(/Candidate group 12 ·/)
        : screen.getByText("Excluded documents (1)")
    await act(async () => {
      summary.click()
    })
    const group = summary.closest("details")!
    const copy =
      action === "exclude"
        ? within(group).getByRole("listitem", {
            name: "Copy 2: Monthly statements.txt",
          })
        : group
    const trigger = within(copy).getByRole("button", {
      name:
        action === "exclude"
          ? "Exclude this copy; retain Monthly statements.txt"
          : "Restore Monthly statements.txt",
    })
    trigger.scrollIntoView({ block: "center" })
    await act(async () => {
      trigger.click()
    })
    const heading = await screen.findByRole("heading", {
      name:
        action === "exclude"
          ? "Confirm duplicate exclusion"
          : "Restore excluded document",
    })
    expect(heading).toHaveFocus()
    expect(heading.getBoundingClientRect().top).toBeGreaterThanOrEqual(0)
    expect(heading.getBoundingClientRect().bottom).toBeLessThanOrEqual(900)
    const form = screen.getByRole("form", { name: "Duplicate decision" })
    const candidate = within(form).getByRole("region", {
      name: action === "exclude" ? "Copy to exclude" : "Copy to restore",
    })
    expect(candidate).toHaveTextContent("Monthly statements.txt")
    expect(candidate).toHaveTextContent("0 stored rows")
    expect(candidate).toHaveTextContent(
      "Example Bank · Synthetic company 12 · Account 00120011 · USD · 2026-02-01 to 2026-02-28"
    )
    if (action === "exclude")
      expect(
        within(form).getByRole("region", { name: "Copy to keep" })
      ).toHaveTextContent("2026-01-01 to 2026-01-31")
    await page.screenshot({
      element: form,
      path: `/tmp/loupe-duplicate-${action}-confirmation.png`,
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Close decision", exact: true })
        .click()
    })
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(trigger.getBoundingClientRect().top).toBeGreaterThanOrEqual(0)
    expect(trigger.getBoundingClientRect().bottom).toBeLessThanOrEqual(900)
    expect(group).toHaveAttribute("open")
    expect(screen.getByText("Reading groups 11–12 of 12")).toBeVisible()
    expect(requests).toHaveBeenCalledTimes(1)
    view.unmount()
    client.clear()
  })
}

for (const width of [1280, 390]) {
  it(`keeps a 52-period original-file group compact and preserves every exact source at ${width}px`, async () => {
    await page.viewport(width, 900)
    const data = duplicateContextCandidates(2)
    const members = data.groups[1].members
    for (const [copy, member] of members.entries()) {
      member.statement_context = Array.from({ length: 52 }, (_, index) => {
        const account = Math.floor(index / 24)
        return {
          period_id: `large-period-${copy}-${index}`,
          account_id: `large-account-${account}`,
          bank: "Example · Bank",
          account_holder: "Synthetic · company",
          account_number: `000${account + 1}`,
          currency: account === 2 ? "EUR" : "USD",
          period_start: new Date(Date.UTC(2020, index, 1))
            .toISOString()
            .slice(0, 10),
          period_end:
            copy === 1 && index === 1
              ? null
              : new Date(Date.UTC(2020, index + 1, 0))
                  .toISOString()
                  .slice(0, 10),
        }
      })
    }
    data.groups = [data.groups[0]]
    data.source_hash_groups = [
      {
        sha256_at_ingestion: "d".repeat(64),
        members,
        limitation:
          "Same recorded file checksum; saved statement details differ. This does not establish duplicate payments.",
      },
    ]
    const last = members[1].statement_context[51]
    const reads: string[] = []
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      expect(options?.method || "GET").toBe("GET")
      const path = String(url)
      reads.push(path)
      if (path === "/api/financial/duplicates?case_id=case-1")
        return new Response(JSON.stringify(data))
      if (
        path ===
        `/api/financial/statement-periods/${last.period_id}/source?case_id=case-1`
      )
        return new Response(
          JSON.stringify({
            case_id: "case-1",
            period_id: last.period_id,
            source_document_id: members[1].document_id,
            evidence_file_id: members[1].evidence_file_id,
            filename: members[1].filename,
            recorded_digest_matches: true,
            file_bytes_verified: false,
            limitation: "Original file retained; exact page not established.",
          })
        )
      throw Error(`Unexpected read ${path}`)
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <main className="p-4">
            <DuplicateCandidatesPanel caseId="case-1" showCrossCase={false} />
          </main>
        </MemoryRouter>
      </QueryClientProvider>
    )
    await act(async () => {
      await page
        .getByRole("button", { name: "Compare documents", exact: true })
        .click()
    })
    const heading = await screen.findByRole("heading", {
      name: "Same original file, different statement details",
    })
    const section = heading.closest("section")!
    const summary = within(section).getByText(/Original file group 1 ·/)
    expect(summary).toHaveTextContent(
      "104 saved periods across 2 copies · 3 recorded account/currency combinations"
    )
    expect(summary).toHaveTextContent(
      "Example · Bank · Synthetic · company · Account 0001 · USD"
    )
    expect(summary).toHaveTextContent("1 with missing dates")
    expect(summary).toHaveTextContent("1 more account/currency combinations")
    expect(summary).toHaveTextContent(
      "Open group for all 104 saved periods and their sources. Date spans may contain gaps."
    )
    expect(summary.textContent).not.toContain("2024-04-30")
    expect(summary.getBoundingClientRect().height).toBeLessThan(
      width === 1280 ? 200 : 370
    )
    expect(section.getBoundingClientRect().height).toBeLessThan(
      width === 1280 ? 260 : 470
    )
    const candidate = screen.getByText(/Candidate group 1 ·/)
    expect(candidate.getBoundingClientRect().bottom).toBeLessThan(900)
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      element: screen.getByRole("main"),
      path: `/tmp/loupe-duplicate-52-periods-${width}-collapsed.png`,
    })
    await act(async () => {
      summary.click()
    })
    const lists = within(section).getAllByRole("list", {
      name: "Saved statement periods",
    })
    expect(lists).toHaveLength(2)
    expect(
      within(lists[1]).getAllByRole("button", {
        name: /Inspect statement source/,
      })
    ).toHaveLength(52)
    const trigger = within(lists[1]).getByRole("button", {
      name: "Inspect statement source · 2024-04-01 to 2024-04-30 · EUR",
    })
    trigger.scrollIntoView({ block: "center" })
    await act(async () => {
      trigger.click()
    })
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent(
      "Account 0003 · EUR · 2024-04-01 to 2024-04-30"
    )
    await within(dialog).findByRole("button", { name: "Open statement file" })
    await act(async () => {
      await page
        .getByRole("button", {
          name: "Back to duplicate comparison",
          exact: true,
        })
        .click()
    })
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(summary.closest("details")).toHaveAttribute("open")
    expect(reads).toEqual([
      "/api/financial/duplicates?case_id=case-1",
      `/api/financial/statement-periods/${last.period_id}/source?case_id=case-1`,
    ])
    view.unmount()
    client.clear()
  })
}
