import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import {
  DuplicateDecisionForm,
  type DuplicateSelection,
} from "./DuplicateDecisionForm"

afterEach(() => vi.restoreAllMocks())
const selection: DuplicateSelection = {
  caseId: "original-case",
  document: {
    document_id: "copy",
    filename: "copy.ofx",
    revision: "a".repeat(64),
  },
  primary: {
    document_id: "kept",
    filename: "kept.ofx",
    revision: "b".repeat(64),
  },
}
function mount(selected = selection) {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, "invalidateQueries")
  render(
    <QueryClientProvider client={client}>
      <DuplicateDecisionForm selection={selected} onClose={vi.fn()} />
    </QueryClientProvider>
  )
  return invalidate
}
function submit() {
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Confirmed duplicate" },
  })
  fireEvent.submit(screen.getByRole("form", { name: "Duplicate decision" }))
}
it("sends one decision with reviewed revisions and invalidates its original case", async () => {
  let finish!: (value: Response) => void
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const invalidate = mount()
  submit()
  fireEvent.submit(screen.getByRole("form", { name: "Duplicate decision" }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  const [url, options] = fetch.mock.calls[0]
  expect(String(url)).toContain("case_id=original-case")
  expect(JSON.parse(String(options?.body))).toEqual({
    action: "exclude",
    reason: "Confirmed duplicate",
    primary_id: "kept",
    expected_revision: "a".repeat(64),
    expected_primary_revision: "b".repeat(64),
  })
  finish(
    new Response(
      JSON.stringify({
        case_id: "original-case",
        document_id: "copy",
        action: "exclude",
        applied: true,
        changed_rows: 2,
        adjudication_id: "event",
      })
    )
  )
  expect(await screen.findByRole("status")).toHaveTextContent("2 rows excluded")
  expect(screen.queryByRole("button", { name: "Record decision" })).toBeNull()
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-decisions", "original-case"],
  })
})
it.each([409, 500, 200])(
  "does not call an unconfirmed response success or retry it (%s)",
  async (status) => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify(
              status === 200 ? { applied: false } : { detail: "Changed" }
            ),
            { status }
          )
      )
    mount()
    submit()
    expect(await screen.findByRole("alert")).toHaveTextContent(
      status === 409 ? "Decision refused" : "may have been recorded"
    )
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: "Record decision" })).toBeNull()
  }
)
it("restoration sends no primary and explains the effect on totals", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: "Legacy exclusion" }), {
          status: 409,
        })
    )
  mount({ ...selection, primary: undefined })
  expect(screen.getByText(/Both copies may then count/)).toBeInTheDocument()
  submit()
  await screen.findByRole("alert")
  const body = JSON.parse(String(fetch.mock.calls[0][1]?.body))
  expect(body.action).toBe("restore")
  expect(body).not.toHaveProperty("primary_id")
})
