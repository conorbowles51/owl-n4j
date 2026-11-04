import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

/** 07 J-13 steps 1, 5 and 6 and "[name] is also reviewing this thread." with the server stubbed. Synthetic only. */
const share = vi.hoisted(() => ({
  previewSplit: vi.fn(),
  makeSplit: vi.fn(),
  presenceBeat: vi.fn(),
  getThreadReviewState: vi.fn(),
  recordSecondPass: vi.fn(),
  getReviewCoverage: vi.fn(),
  startSecondPass: vi.fn(),
}))
const members = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock("@/features/phones/review-share", async (orig) => ({ ...(await orig<object>()), ...share }))
vi.mock("@/features/cases/members-api", () => ({ caseMembersAPI: members }))

import { ApiError } from "@/lib/api-client"
import { ReviewCoverage } from "@/features/phones/summary/ReviewCoverage"
import { SplitForReview } from "./SplitForReview"
import { ThreadReviewBar } from "./ThreadReviewBar"
import { PRESENCE_BEAT_MS } from "./use-thread-presence"

const people = [
  { user_id: "u-ann", user_name: "Ann Synthetic", user_email: "a@x.test", preset: "owner", permissions: {} },
  { user_id: "u-bea", user_name: "Bea Synthetic", user_email: "b@x.test", preset: "editor", permissions: {} },
  { user_id: "u-viv", user_name: "Viv Viewer", user_email: "v@x.test", preset: "viewer", permissions: {} },
]
const plan = {
  by: "thread", only_not_reviewed: true, threads_in_filter: 5, threads: 4, messages: 9, already_reviewed_left_out: 1,
  parts: [
    { part: 1, reviewer: { user_id: "u-ann", name: "Ann Synthetic" }, threads: 2, messages: 5, people: 0, words: "Ann Synthetic: 2 threads, 5 messages" },
    { part: 2, reviewer: { user_id: "u-bea", name: "Bea Synthetic" }, threads: 2, messages: 4, people: 0, words: "Bea Synthetic: 2 threads, 4 messages" },
  ],
  words: "4 threads into 2 tasks, by thread; 1 thread already reviewed is left out.", warning: null,
}

function wrap(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.useRealTimers()
  Object.values(share).forEach((f) => f.mockReset())
})

describe("Split for review (07 J-13 step 1)", () => {
  it("shows the counts before making anything, offers only people who can mark, and makes the tasks with the count seen", async () => {
    members.list.mockResolvedValue(people)
    share.previewSplit.mockResolvedValue(plan)
    share.makeSplit.mockResolvedValue({ split_id: "s1", threads: 4, words: "Made 2 review tasks for 4 threads.", tasks: [
      { task_id: "t1", title: "Review phone conversations, part 1 of 2 (by thread)", reviewer: plan.parts[0].reviewer, threads: 2, messages: 5 },
      { task_id: "t2", title: "Review phone conversations, part 2 of 2 (by thread)", reviewer: plan.parts[1].reviewer, threads: 2, messages: 4 },
    ] })
    wrap(<SplitForReview caseId="case-1" filter={{ case_id: "case-1" }} scopeWords="All phones" open onClose={() => {}} />)
    expect(await screen.findByLabelText("Ann Synthetic")).toBeInTheDocument()
    expect(screen.queryByLabelText("Viv Viewer")).toBeNull()
    expect(screen.getByRole("button", { name: "Choose who reviews" })).toBeDisabled()
    fireEvent.click(screen.getByLabelText("Ann Synthetic"))
    fireEvent.click(screen.getByLabelText("Bea Synthetic"))
    fireEvent.click(screen.getByRole("button", { name: "Show the counts" }))
    expect(await screen.findByText(plan.words)).toBeInTheDocument()
    expect(screen.getByText("Bea Synthetic: 2 threads, 4 messages")).toBeInTheDocument()
    expect(share.makeSplit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Make 2 review tasks" }))
    await waitFor(() => expect(share.makeSplit).toHaveBeenCalledWith(expect.objectContaining({ expect_threads: 4, reviewers: ["u-ann", "u-bea"], by: "thread" })))
    expect(await screen.findByText("Made 2 review tasks for 4 threads.")).toBeInTheDocument()
  })

  it("makes nothing and asks for new counts when the threads changed since they were shown", async () => {
    members.list.mockResolvedValue(people)
    share.previewSplit.mockResolvedValue(plan)
    share.makeSplit.mockRejectedValue(new ApiError("The threads changed since the counts were shown: 5 now. Check the split again.", 409))
    wrap(<SplitForReview caseId="case-1" filter={{ case_id: "case-1" }} scopeWords="" open onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText("Ann Synthetic"))
    fireEvent.click(screen.getByRole("button", { name: "Show the counts" }))
    fireEvent.click(await screen.findByRole("button", { name: "Make 2 review tasks" }))
    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Show the counts" })).toBeEnabled()
  })
})

describe("[name] is also reviewing this thread (07 J-13 failure state)", () => {
  it("names the other person, beats under once per 30 s while open, and leaves when the thread closes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    share.presenceBeat.mockResolvedValue({ thread_key: "k1", others: ["Bea Synthetic"], words: "Bea Synthetic is also reviewing this thread.", next_in_seconds: 45 })
    share.getThreadReviewState.mockResolvedValue({ thread_key: "k1", tasks: [], second_pass: [] })
    const view = wrap(<ThreadReviewBar caseId="case-1" threadKey="k1" />)
    expect(await screen.findByText("Bea Synthetic is also reviewing this thread.")).toBeInTheDocument()
    expect(share.presenceBeat).toHaveBeenCalledTimes(1)
    expect(PRESENCE_BEAT_MS).toBeGreaterThan(30_000)
    await act(async () => { vi.advanceTimersByTime(60_000) })
    expect(share.presenceBeat).toHaveBeenCalledTimes(2) // one minute open: 2 beats, under 1 per 30 s
    await act(async () => { vi.advanceTimersByTime(120_000) })
    expect(share.presenceBeat.mock.calls.length).toBeLessThanOrEqual(1 + Math.floor(180_000 / 30_000) - 1)
    view.unmount()
    await waitFor(() => expect(share.presenceBeat).toHaveBeenLastCalledWith("case-1", "k1", true))
  })
})

describe("Second pass (07 J-13 step 5)", () => {
  it("shows the first review beside the sample and needs a note to disagree", async () => {
    share.presenceBeat.mockResolvedValue({ thread_key: "k1", others: [], words: null, next_in_seconds: 45 })
    share.getThreadReviewState.mockResolvedValue({ thread_key: "k1", tasks: [{ task_id: "t1", title: "Review phone conversations, part 1 of 2 (by thread)", assigned_to_name: "Ann Synthetic", mine: false }], second_pass: [{
      first: { reviewed_by_name: "Ann Synthetic", record_count: 12 }, result: null, earlier_results: 0, assigned_to: "u-bea", assigned_to_name: "Bea Synthetic",
      seed: 77, percent: 10, words: "In a second-pass sample for Bea Synthetic; no result yet.", task_id: "sp1", title: "Second-pass review", mine: true }] })
    share.recordSecondPass.mockResolvedValue({})
    wrap(<ThreadReviewBar caseId="case-1" threadKey="k1" />)
    expect(await screen.findByText(/First review by Ann Synthetic \(12 messages\), kept as it is\./)).toBeInTheDocument()
    expect(screen.getByText(/In review task "Review phone conversations, part 1 of 2 \(by thread\)", assigned to Ann Synthetic\./)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Disagrees" })).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Second-pass note"), { target: { value: "missed a reply" } })
    fireEvent.click(screen.getByRole("button", { name: "Disagrees" }))
    await waitFor(() => expect(share.recordSecondPass).toHaveBeenCalledWith("case-1", "sp1", "k1", false, "missed a reply"))
  })
})

describe("Coverage summary (07 J-13 step 6)", () => {
  it("lists who reviewed what, the tasks, the second pass, the searches run and every thread not yet reviewed", async () => {
    share.getReviewCoverage.mockResolvedValue({
      counts: { threads: 3, reviewed: 1, partly_reviewed: 1, not_reviewed: 2, never_reviewed: 1 },
      words: "", cover: [], keyword_lists: [], terms: ["apple"],
      reviewers: [{ name: "Ann Synthetic", reviewed: 1, partly_reviewed: 1, messages_at_review: 4 }],
      not_reviewed: [{ thread_key: "k3", title: "Synthetic three", phone: "C3", messages: 2, review: null, added_since: null }],
      partly_reviewed: [{ thread_key: "k2", title: "Synthetic two", phone: "C3", messages: 3, review: "Reviewed by Ann Synthetic on Nov 3 (2 messages); 1 added since", added_since: 1 }],
      reviewed: [],
      splits: [{ task_id: "t1", title: "Review phone conversations, part 1 of 1 (by thread)", status: "in_progress", reviewer: "Ann Synthetic", threads: 3, reviewed: 1, words: "Review phone conversations, part 1 of 1 (by thread) (Ann Synthetic): 1 of 3 threads reviewed" }],
      second_pass: [{ pass_id: "p1", task_id: "sp1", title: "x", seed: 77, percent: 10, eligible: 1, reviewer: "Bea Synthetic", sampled: 1, agrees: 0, disagrees: 1, pending: 0,
        disagreements: [{ thread_key: "k1", title: "Synthetic one", by: "Bea Synthetic", first_by: "Ann Synthetic", note: "missed a reply" }] }],
      searches: [{ query: "apple", exact: false, runs: 2, people: ["Ann Synthetic"], surfaces: ["conversations"], last_hits: 2, last_run_at: "2026-11-03T00:00:00Z" }],
    })
    wrap(<ReviewCoverage caseId="case-1" extraction="e1" />)
    expect(await screen.findByText("Not yet reviewed: 2 of 3 threads")).toBeInTheDocument()
    expect(screen.getByTestId("reviewed-by")).toHaveTextContent("Reviewed by: Ann Synthetic, 1 thread and 1 partly.")
    expect(screen.getByText("Threads not yet reviewed (1)")).toBeInTheDocument()
    expect(screen.getByText("Review phone conversations, part 1 of 1 (by thread) (Ann Synthetic): 1 of 3 threads reviewed")).toBeInTheDocument()
    expect(screen.getByText(/10% sample \(seed 77\) for Bea Synthetic: 1 sampled, 0 agree, 1 disagree/)).toBeInTheDocument()
    expect(screen.getByText(/Bea Synthetic disagrees with Ann Synthetic's review of "Synthetic one": missed a reply/)).toBeInTheDocument()
    expect(screen.getByTestId("searches-run")).toHaveTextContent('"apple": run 2 times by Ann Synthetic; 2 found the last time')
  })
})
