import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it, vi } from "vitest"
import { RecycleBinPanel } from "./RecycleBinPanel"

vi.mock("../api", () => ({
  graphAPI: { listRecycledEntities: vi.fn().mockResolvedValue({ items: [] }) },
}))
vi.mock("@/features/financial/components/LoadProgress", () => ({ LoadProgress: () => null }))

it("says how long a deleted entity is kept: until restored or deleted permanently", async () => {
  // Evidence's Deleted items says 30 days; graph entities are never purged on a timer (deleted_items.py purge=False).
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RecycleBinPanel caseId="case-1" />
    </QueryClientProvider>
  )
  expect(await screen.findByText("Deleted entities stay here until someone restores them or deletes them permanently.")).toBeVisible()
  expect(screen.getByText("0 items")).toBeVisible()
})
