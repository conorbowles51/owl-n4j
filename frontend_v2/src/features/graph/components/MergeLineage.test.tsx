import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { MergeLineage } from "./MergeLineage"

const lineage = vi.hoisted(() => vi.fn())
vi.mock("../api", () => ({ graphAPI: { getMergeLineage: lineage } }))

function show(entityKey: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MergeLineage caseId="c1" entityKey={entityKey} /></QueryClientProvider>)
}

it("shows the names and keys a merged entity was made from, who merged them and when", async () => {
  lineage.mockResolvedValue({
    entity_key: "person:ann-smith",
    merges: [{ merge_job_id: "m1", into: "person:ann-smith", by: "Investigator", at: "2026-11-15T05:00:00Z",
               status: "completed", sources: [{ key: "person:ann", name: "Ann" }, { key: "person:bob", name: null }] }],
  })
  show("person:ann-smith")
  const box = within(await screen.findByRole("region", { name: "Merged from" }))
  expect(box.getByText("On 2026-11-15, Investigator merged:")).toBeTruthy()
  expect(box.getByText("Ann")).toBeTruthy()
  expect(box.getByText("(person:ann)")).toBeTruthy()
  expect(box.getByText("No name on record")).toBeTruthy()
  expect(lineage).toHaveBeenCalledWith("c1", "person:ann-smith")
})

it("shows nothing for an entity that was never a merge", async () => {
  lineage.mockResolvedValue({ entity_key: "person:zed", merges: [] })
  const view = show("person:zed")
  await new Promise((r) => setTimeout(r, 20))
  expect(view.container.textContent).toBe("")
})
