import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useCaseLayerStore } from "@/features/significant/stores/case-layer.store"
import { SignificantNote } from "./SignificantNote"

const api = vi.hoisted(() => ({ getSignificantSummary: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

const show = (on: boolean, onChange = vi.fn(), hiddenWords?: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SignificantNote caseId="c" on={on} onChange={onChange} hiddenWords={hiddenWords} />
    </QueryClientProvider>,
  )

describe("SignificantNote (07 XF-11)", () => {
  beforeEach(() => {
    useCaseLayerStore.setState({ layerByCase: {} })
    api.getSignificantSummary.mockResolvedValue({ case_id: "c", significant: 3, total: 41, words: "Phone screens show all records. 3 of 41 phone identities are significant." })
  })

  it("says nothing with the layer off and the toggle off", () => {
    show(false)
    expect(screen.queryByTestId("significant-note")).toBeNull()
    expect(api.getSignificantSummary).not.toHaveBeenCalled()
  })

  it("with the layer on, all records stay shown and the offer is stated", async () => {
    useCaseLayerStore.setState({ layerByCase: { c: "significant" } })
    const onChange = vi.fn()
    show(false, onChange)
    expect(await screen.findByText(/Phone screens show all records\. 3 of 41 phone identities are significant\./)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Show only those" }))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it("narrowed, it says what is hidden and how to get it back", async () => {
    const onChange = vi.fn()
    show(true, onChange, "120 of 500 messages and calls in this view are hidden.")
    expect(await screen.findByText(/Showing only records with the 3 significant phone identities of 41\. 120 of 500/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Show all records" }))
    expect(onChange).toHaveBeenCalledWith(false)
  })

  it("offers no toggle when nothing is significant", async () => {
    useCaseLayerStore.setState({ layerByCase: { c: "significant" } })
    api.getSignificantSummary.mockResolvedValue({ case_id: "c", significant: 0, total: 41, words: "Phone screens show all records. 0 of 41 phone identities are significant." })
    show(false)
    expect(await screen.findByText(/0 of 41/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Show only those" })).toBeNull()
  })
})
