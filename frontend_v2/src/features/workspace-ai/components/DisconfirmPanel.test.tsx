import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { DisconfirmState, DisconfirmSweep } from "../agent-proposals"
import { DisconfirmPanel } from "./DisconfirmPanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const tally = { total: 2, accepted: 1, rejected: 1, waiting: 0, precision: 0.5 }

function sweep(over: Partial<DisconfirmSweep>): DisconfirmSweep {
  return {
    id: "s1",
    case_id: "c1",
    theory_id: "t1",
    theory_title: "Theory",
    stage: "planned",
    step: "Ready",
    job_status: "completed",
    progress: 100,
    error: null,
    cancel_requested: false,
    started_at: null,
    completed_at: null,
    model: { provider: "deepseek", model_id: "deepseek-v4-pro", others_configured: [], words: "One model read this." },
    expectations: [{ id: "E1", claim: "No payment to Ashdown.", would_contradict: "A payment." }],
    reads: {
      total: 14, done: 0, running: 0, pending: 14, failed: 0, items: 310, items_read: 0, failures: [],
      seconds_per_read: null, slowest_running_seconds: null, slow: false,
    },
    calls_stated: 15,
    time_left: null,
    cost: { usd: 0.01, tokens: 900, calls: 1 },
    proposals: [],
    refused: [],
    repeats: [],
    absences: null,
    outcome: {
      headline: "", complete: false, findings: 0, not_read: 14, absences: 0,
      not_support: "A sweep cannot show a theory is right.", expectations: [],
    },
    ...over,
  }
}

function show(state: Partial<DisconfirmState>) {
  vi.mocked(fetchAPI).mockResolvedValue({
    sweep: null, tally: { counter_arguments: tally, red_cell: tally }, counter_arguments: [], ...state,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DisconfirmPanel caseId="c1" theoryId="t1" canEdit />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("DisconfirmPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchAPI).mockReset()
  })

  it("states the cost of the first press, and the counts beside the red cell's", async () => {
    show({})
    expect(await screen.findByRole("button", { name: /Look for what breaks it \(one model call\)/ })).toBeTruthy()
    expect((await screen.findByTestId("disconfirm-tally")).textContent).toContain("Red cell: 2 proposed")
  })

  it("shows progress on the press, before the server answers", async () => {
    show({})
    const press = await screen.findByRole("button", { name: /Look for what breaks it/ })
    vi.mocked(fetchAPI).mockReturnValue(new Promise(() => undefined))
    fireEvent.click(press)
    expect((await screen.findByTestId("disconfirm-progress")).textContent).toContain("start the sweep")
  })

  it("shows the sweep from the press's own answer, with no second request", async () => {
    show({})
    const press = await screen.findByRole("button", { name: /Look for what breaks it/ })
    const running = sweep({ stage: "planning", job_status: "running", step: "Reading the theory", progress: 2 })
    let answered = false
    vi.mocked(fetchAPI).mockImplementation(async () => {
      if (answered) return new Promise(() => undefined)
      answered = true
      return running
    })
    fireEvent.click(press)
    expect((await screen.findByTestId("disconfirm-progress")).textContent).toContain("Reading the theory")
  })

  it("gives the exact count before any read starts", async () => {
    show({ sweep: sweep({}) })
    expect((await screen.findByTestId("disconfirm-plan")).textContent).toContain(
      "The searches matched 310 items. Reading them takes 14 model calls"
    )
    expect(screen.getByRole("button", { name: "Run all 14 reads" })).toBeTruthy()
    expect(screen.getByText("No payment to Ashdown.")).toBeTruthy()
  })

  it("shows the step, true counts, an estimate labelled as one, and a slow read", async () => {
    show({
      sweep: sweep({
        stage: "reading", job_status: "running", step: "Read 3 of 14; 4 running", progress: 21,
        started_at: new Date().toISOString(), time_left: { seconds: 90, label: "estimate, not measured" },
        reads: {
          total: 14, done: 3, running: 4, pending: 7, failed: 0, items: 310, items_read: 60, failures: [],
          seconds_per_read: 40, slowest_running_seconds: 200, slow: true,
        },
      }),
    })
    const panel = await screen.findByTestId("disconfirm-progress")
    expect(panel.textContent).toContain("Read 3 of 14; 4 running")
    expect(panel.textContent).toContain("3 of 14 reads done, 4 running")
    expect(panel.textContent).toContain("(estimate, not measured)")
    expect(screen.getByTestId("disconfirm-slow").textContent).toContain("3 min 20 s")
    expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy()
  })

  it("names a failed read and offers only what is left", async () => {
    show({
      sweep: sweep({
        stage: "done", reads: {
          total: 14, done: 13, running: 0, pending: 0, failed: 1, items: 310, items_read: 300,
          failures: [{ id: "E2.1", expectation: "E2", error: "ReadTimeout" }],
          seconds_per_read: 40, slowest_running_seconds: null, slow: false,
        },
      }),
    })
    expect(await screen.findByText(/Read E2.1 did not finish: ReadTimeout/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Run the 1 remaining read" })).toBeTruthy()
  })

  it("never lets nothing found read as support: searched, out of reach, absences", async () => {
    show({
      sweep: sweep({
        stage: "done",
        reads: { ...sweep({}).reads, done: 14, pending: 0 },
        outcome: {
          headline: "All 14 reads finished. Nothing was found against the theory in what was read. That is not support for the theory.",
          complete: true, findings: 0, not_read: 0, absences: 1, not_support: "A sweep cannot show a theory is right.",
          expectations: [{
            id: "E1", claim: "No payment.", reads: 1, unread: 0, findings: 0, repeats: 0,
            searched: ["ledger: 3 searches of 65 rows"], out_of_reach: ["phones: The case holds no phone."],
            sentence: "Nothing found against this expectation in what was searched. That is not support for the theory.",
          }],
        },
        absences: {
          items: [{ kind: "phone", what: "A phone of Ashdown", reason: "No phone has this owner.", expectation: "E1" }],
          not_checked: [], needs: 1, limitation: "A gap means the case holds no record of it.",
        },
      }),
    })
    const result = await screen.findByTestId("disconfirm-result")
    expect(result.textContent).toContain("That is not support for the theory.")
    expect(screen.getByTestId("disconfirm-out-of-reach").textContent).toContain("The case holds no phone.")
    expect(screen.getByTestId("disconfirm-absences").textContent).toContain("A phone of Ashdown")
  })

  it("shows an accepted counter-argument under the model that wrote it", async () => {
    show({
      counter_arguments: [{
        id: "p1", case_id: "c1", output_type: "counter_argument", review_status: "accepted", content: { title: "A payment" },
        citations: [], proposal: { kind: "counter_argument", model: "deepseek-v4-pro" }, accepted_by: "Alex",
        model_text: "The row shows it.", person_text: null,
      }],
    })
    expect((await screen.findByTestId("counter-arguments")).textContent).toContain(
      "Written by deepseek-v4-pro, accepted by Alex"
    )
  })
})
