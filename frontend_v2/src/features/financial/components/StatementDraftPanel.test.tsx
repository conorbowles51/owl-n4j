import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { StatementDraftPanel } from "./StatementDraftPanel"
import type { StatementScope } from "../lib/statement-scope-contract"
afterEach(() => vi.restoreAllMocks())
const cell = {
  page_number: 1,
  table_index: 0,
  row_index: 0,
  column_index: 0,
  source_revision: "c".repeat(64),
  expected_text: "Dates",
}
const scope: StatementScope = {
  account_id: "9445f4da-ed83-4819-9ce2-059cb259790a",
  currency: "GBP",
  candidate_ids: ["7b74f9db-9ff4-4325-a966-ddda8e957879"],
  start: { value: "2026-02-01", source: cell },
  end: { value: "2026-02-28", source: cell },
  opening: null,
  closing: null,
  balance_convention: "asset_balance",
  reason: "Reviewed dates",
}
const empty = {
  case_id: "case",
  evidence_file_id: "file",
  statement_scopes: [],
  revision: null,
  saved_at: null,
  applied: false,
}
function mount(initial: unknown = empty, conflict = false) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_url, options) => {
      if (options?.method === "PUT") {
        if (conflict)
          return new Response(
            JSON.stringify({ detail: "Saved controls changed" }),
            { status: 409 }
          )
        return new Response(
          JSON.stringify({
            ...empty,
            statement_scopes: JSON.parse(String(options.body)).statement_scopes,
            revision: "a".repeat(64),
            saved_at: "2026-09-10T03:00:00Z",
          })
        )
      }
      return new Response(JSON.stringify(initial))
    })
  const load = vi.fn()
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <StatementDraftPanel
        caseId="case"
        fileId="file"
        scopes={[scope]}
        onLoad={load}
        disabled={false}
      />
    </QueryClientProvider>
  )
  return { fetch, load, client }
}
it("saves controls with the observed revision and reports durable success", async () => {
  const { fetch } = mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Save statement controls to case",
    })
  )
  expect(
    await screen.findByText("Statement controls saved to this case.")
  ).toBeInTheDocument()
  const body = JSON.parse(
    String(
      fetch.mock.calls.find(([, opts]) => opts?.method === "PUT")![1]?.body
    )
  )
  expect(body.expected_revision).toBeNull()
  expect(body.statement_scopes).toEqual([scope])
})
it("existing drafts must be loaded before replacement", async () => {
  const { load } = mount({
    ...empty,
    statement_scopes: [{ ...scope, reason: "Earlier work" }],
    revision: "b".repeat(64),
  })
  expect(
    await screen.findByRole("button", {
      name: "Save statement controls to case",
    })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Load saved statement controls" })
  )
  expect(load).toHaveBeenCalledWith([{ ...scope, reason: "Earlier work" }])
})
it("reports conflicts without pretending the draft saved", async () => {
  mount(empty, true)
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Save statement controls to case",
    })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("not saved")
  expect(
    screen.queryByText("Statement controls saved to this case.")
  ).not.toBeInTheDocument()
})

it("requires reloading when a newer draft arrives in the cache", async () => {
  const { client } = mount({
    ...empty,
    statement_scopes: [{ ...scope, reason: "Earlier work" }],
    revision: "b".repeat(64),
  })
  fireEvent.click(
    await screen.findByRole("button", { name: "Load saved statement controls" })
  )
  expect(
    screen.getByRole("button", { name: "Save statement controls to case" })
  ).toBeEnabled()
  await act(async () => {
    client.setQueryData(["financial-statement-draft", "case", "file"], {
      ...empty,
      statement_scopes: [],
      revision: "c".repeat(64),
    })
  })
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Save statement controls to case" })
    ).toBeDisabled()
  )
})
