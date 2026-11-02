import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 07 J-16 with the server stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({ comparePhones: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { ComparePhones } from "./ComparePhones"

const side = (id: string, label: string, noTime = 0) => ({ extraction_id: id, label, first: null, last: null, no_time: noTime })

describe("Compare phones", () => {
  it("compares the first two phones: on both, only on each with what falls outside the other's period", async () => {
    api.comparePhones.mockResolvedValue({
      case_id: "case-1", person: null, a: side("e1", "C1", 2), b: side("e2", "C3"), key: "Matched by app, time and text.",
      kinds: { message: { both: 1204, only_a: 30, only_a_outside: 12, only_b: 1, only_b_outside: 0 }, call: { both: 0, only_a: 0, only_a_outside: 0, only_b: 4, only_b_outside: 0 } },
    })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ComparePhones caseId="case-1" phones={[{ extraction_id: "e1", label: "C1" }, { extraction_id: "e2", label: "C3" }, { extraction_id: "e3", label: "C2" }]} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(api.comparePhones).toHaveBeenCalledWith("case-1", "e1", "e2", null, expect.anything()))
    expect(await screen.findByText("1,204 on both")).toBeInTheDocument()
    expect(screen.getByText("30 only on C1")).toBeInTheDocument()
    expect(screen.getByText("12 outside C3's period")).toBeInTheDocument()
    expect(screen.getByText("4 only on C3")).toBeInTheDocument()
    expect(screen.getByText("2 messages and calls on C1 have no time and are not compared.")).toBeInTheDocument()
  })
})
