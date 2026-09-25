import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementRecoveryPanel } from "./StatementRecoveryPanel"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
const data = {
  run: { id: "run", status: "running", release: "test" },
  total: 2,
  counts: { review: 1, waiting: 1 },
  items: [
    {
      id: "item",
      file_id: "original",
      review_file_id: "retained-reading",
      filename: "Synthetic statement.pdf",
      status: "review",
      added: 0,
      message: "A manually added payment needs comparison.",
      sections: [],
    },
  ],
}
function mount(onReview = vi.fn()) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false, gcTime: 0 } },
        })
      }
    >
      <StatementRecoveryPanel caseId="case" onReview={onReview} />
    </QueryClientProvider>
  )
}
it("shows progress, pauses, resumes and opens the retained reading", async () => {
  let status = "running"
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      status = url.includes("/pause?") ? "paused" : "running"
      return { status } as never
    }
    return { ...data, run: { ...data.run, status } } as never
  })
  const open = vi.fn()
  mount(open)
  expect(await screen.findByRole("status")).toHaveTextContent(
    "1 of 2 files checked · 1 need review"
  )
  fireEvent.click(screen.getByRole("button", { name: "Pause recovery" }))
  fireEvent.click(
    await screen.findByRole("button", { name: "Resume recovery" })
  )
  await screen.findByRole("button", { name: "Pause recovery" })
  fireEvent.click(screen.getByText("Review recovery results"))
  fireEvent.click(screen.getByRole("button", { name: "Open statement" }))
  expect(open).toHaveBeenCalledWith("retained-reading")
  fireEvent.click(screen.getByRole("button", { name: "Retry recovery" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("items/item/retry?case_id=case"),
      { method: "POST" }
    )
  )
})
it("keeps the outcome visible if retry cannot be confirmed", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "POST") throw Error("Connection interrupted")
    return { ...data, run: { ...data.run, status: "complete" } } as never
  })
  mount()
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Finished checking"
  )
  fireEvent.click(screen.getByText("Review recovery results"))
  fireEvent.click(screen.getByRole("button", { name: "Retry recovery" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Connection interrupted"
  )
  expect(
    screen.getByText("A manually added payment needs comparison.")
  ).toBeVisible()
})

it("reports only the scheduled follow-up results while explaining protected and unknown sources", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...data,
    run: { ...data.run, status: "complete" },
    counts: { review: 1, kept: 1 },
    scope: {
      considered: 19,
      scheduled: 2,
      protected: 3,
      no_unresolved_work: 8,
      unconfirmed_content: 6,
    },
    previous_runs: [{ id: "old-run", release: "earlier", status: "complete" }],
  })
  mount()
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Follow-up finished · 2 of 2 scheduled sources checked · 1 need review"
  )
  expect(
    screen.queryByText(/19 files checked|Finished checking/)
  ).not.toBeInTheDocument()
  expect(screen.getByText(/considered 19 retained sources/)).toHaveTextContent(
    "scheduled 2 with unresolved work"
  )
  expect(screen.getByText(/3 protected sources/)).toHaveTextContent(
    "left unchanged"
  )
  expect(screen.getByText(/8 sources outside this pass/)).toHaveTextContent(
    "Existing statement review checks may still remain"
  )
  expect(screen.getByText(/6 sources not processed/)).toHaveTextContent(
    "Unknown content does not mean a source is non-financial"
  )
})

it("does not present an empty scheduled subset as all sources repaired", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    run: { ...data.run, status: "complete" },
    total: 0,
    counts: {},
    items: [],
    scope: {
      considered: 10,
      scheduled: 0,
      protected: 1,
      no_unresolved_work: 4,
      unconfirmed_content: 5,
    },
  })
  mount()
  expect(await screen.findByRole("status")).toHaveTextContent(
    "0 of 0 scheduled sources checked"
  )
  expect(screen.getByText(/5 sources not processed/)).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Pause recovery" })
  ).not.toBeInTheDocument()
})

it("keeps legacy campaign progress compatible when scope is null", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ ...data, scope: null })
  mount()
  expect(await screen.findByRole("status")).toHaveTextContent(
    "1 of 2 files checked"
  )
  expect(screen.queryByLabelText("Follow-up scope")).not.toBeInTheDocument()
  expect(screen.getByText(/This one-time check/)).toBeVisible()
})
