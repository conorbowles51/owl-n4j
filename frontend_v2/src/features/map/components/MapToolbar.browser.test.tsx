import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { MapToolbar } from "./MapToolbar"

vi.mock("../hooks/use-map-data", () => ({
  useMapReviewQueue: () => ({ data: [] }),
}))

afterEach(() => cleanup())

it("at 390 wide the toolbar wraps inside its column instead of widening the page (lx-overlapviews-b, 18 Nov)", async () => {
  await page.viewport(390, 800)
  render(
    <QueryClientProvider client={new QueryClient()}>
      {/* The map column left between the side menu (64 px) and the right rail (48 px) on a 390-wide phone. */}
      <div style={{ width: 278 }} data-testid="column">
        <MapToolbar caseId="case-1" locations={[]} />
      </div>
    </QueryClientProvider>,
  )
  await screen.findByRole("button", { name: /Areas/ })
  const bar = screen.getByTestId("column").firstElementChild as HTMLElement
  expect(bar.scrollWidth).toBeLessThanOrEqual(278)
  expect(screen.getByTestId("column").scrollWidth).toBeLessThanOrEqual(278)
})
