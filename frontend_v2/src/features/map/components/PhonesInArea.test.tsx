import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import * as api from "@/features/phones/api"
import { PhonesInArea } from "./PhonesInArea"

describe("Map area selection (03 13.3, 07 J-10, XF-6)", () => {
  it("lists every phone seen in the drawn area with its exact count and opens its conversations for that time", async () => {
    const spy = vi.spyOn(api, "getPhoneMapArea").mockResolvedValue({
      case_id: "c", phones_total: 2, points_total: 4, points_without_time: 0, window: { from_instant: null, to_instant: null },
      label: "Investigative location, not cell-site opinion",
      phones: [
        { extraction_id: "e1", phone_label: "C1", points: 3, points_without_time: 0, first: "2023-03-14T12:00:00+00:00", last: "2023-03-14T15:00:00+00:00" },
        { extraction_id: "e2", phone_label: "C2", points: 1, points_without_time: 0, first: "2023-03-14T12:00:00+00:00", last: "2023-03-14T12:00:00+00:00" },
      ],
    })
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>
      <PhonesInArea caseId="c" shape={{ id: "s", coordinates: [[-74, 40], [-73, 40], [-73, 41]] }} />
    </MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText("2 phones, 4 positions inside the area.")).toBeTruthy()
    expect(spy).toHaveBeenCalledWith("c", [[-74, 40], [-73, 40], [-73, 41]], {}, expect.anything())
    expect(screen.getByText("C1: 3 positions")).toBeTruthy()
    const links = screen.getAllByRole("link", { name: "Conversations on this phone at that time" })
    expect(links[0].getAttribute("href")).toBe("/cases/c/conversations?phones=e1&from=2023-03-14T12%3A00%3A00%2B00%3A00&to=2023-03-14T15%3A00%3A00%2B00%3A00&notime=0")
    expect(screen.getByText("Investigative location, not cell-site opinion.")).toBeTruthy()
  })
})
