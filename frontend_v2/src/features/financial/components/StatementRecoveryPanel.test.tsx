import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
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

it("groups identical review reasons within each file without losing distinct reasons or counting other outcomes", async () => {
  const repeated =
    "New reading ready to review. Confirm its account and currency."
  const section = (message: string, status = "review") => ({
    statement_id: null,
    status,
    message,
    added: 0,
  })
  vi.mocked(fetchAPI).mockResolvedValue({
    ...data,
    run: { ...data.run, status: "complete" },
    items: [
      {
        ...data.items[0],
        sections: [
          ...Array.from({ length: 52 }, () => section(repeated)),
          section("Compare an overlap."),
          section("Compare an overlap."),
          section("The saved currency differs."),
          section(repeated, "unchanged"),
        ],
      },
      {
        ...data.items[0],
        id: "second",
        filename: "Second file.pdf",
        file_id: "second-file",
        sections: [section(repeated)],
      },
    ],
  })
  mount()
  await screen.findByRole("status")
  fireEvent.click(screen.getByText("Review recovery results"))
  const first = screen.getByText("Synthetic statement.pdf").closest("li")!
  expect(first).toHaveTextContent("55 sections need review · 3 reasons")
  expect(within(first).getAllByText(repeated)).toHaveLength(1)
  expect(within(first).getByText("52 sections")).toBeVisible()
  expect(within(first).getByText("2 sections")).toBeVisible()
  expect(within(first).getByText("The saved currency differs.")).toBeVisible()
  expect(
    within(first).getByRole("list", { name: "Section review reasons" }).children
  ).toHaveLength(3)
  expect(
    within(first).getByRole("button", { name: "Open statement" })
  ).toBeVisible()
  expect(
    within(first).getByRole("button", { name: "Retry recovery" })
  ).toBeVisible()
  const second = screen.getByText("Second file.pdf").closest("li")!
  expect(second).toHaveTextContent("1 section needs review · 1 reason")
})

it("retains every distinct reason in a keyboard-reachable bounded list", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...data,
    run: { ...data.run, status: "complete" },
    items: [
      {
        ...data.items[0],
        sections: Array.from({ length: 20 }, (_, index) => ({
          statement_id: `section-${index}`,
          status: "review",
          message: `Specific source reason ${index + 1}`,
          added: 0,
        })),
      },
    ],
  })
  mount()
  await screen.findByRole("status")
  fireEvent.click(screen.getByText("Review recovery results"))
  const reasons = screen.getByRole("list", { name: "Section review reasons" })
  expect(reasons).toHaveAttribute("tabindex", "0")
  expect(within(reasons).getAllByRole("listitem")).toHaveLength(20)
  expect(reasons).toHaveTextContent("Specific source reason 20")
})

it("counts blank review messages while explaining that their sections still need review", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...data,
    run: { ...data.run, status: "complete" },
    items: [
      {
        ...data.items[0],
        sections: ["", "  \n"].map((message) => ({
          statement_id: null,
          status: "review",
          message,
          added: 0,
        })),
      },
    ],
  })
  mount()
  await screen.findByRole("status")
  fireEvent.click(screen.getByText("Review recovery results"))
  expect(screen.getByText("2 sections need review · 1 reason")).toBeVisible()
  expect(screen.getByText("Review this statement section.")).toBeVisible()
})
