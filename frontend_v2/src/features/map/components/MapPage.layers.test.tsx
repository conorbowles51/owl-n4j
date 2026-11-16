import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { resetRequestsForTest } from "@/lib/request-progress"
import { TooltipProvider } from "@/components/ui/tooltip"

const canvas = vi.fn()
vi.mock("./MapCanvas", () => ({ MapCanvas: (p: { phoneColours?: Record<string, string> }) => { canvas(p); return <div data-testid="map-canvas" /> } }))
const A = "aaaaaaaa-0000-4000-8000-000000000001", B = "bbbbbbbb-0000-4000-8000-000000000002", C = "cccccccc-0000-4000-8000-000000000003"
const api = vi.hoisted(() => ({
  getPhones: vi.fn(),
  getPhoneMapSummary: vi.fn(),
  getPhoneMapPoints: vi.fn(),
  getPhoneMapTrajectory: vi.fn(),
}))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
import { MapPage } from "./MapPage"

const CASE = "c0ffee00-0000-4000-8000-000000000001"
const phone = (id: string, label: string) => ({ extraction_id: id, label })
const summary = (n: number) => ({ case_id: CASE, positioned: n, total: n, by_source: {}, not_positionable: [], bbox: [-74, 40, -73, 41],
  by_phone: [{ extraction_id: A, label: "Phone 1", positioned: 412 }, { extraction_id: B, label: "Phone 2", positioned: 230 }, { extraction_id: C, label: "Phone 3", positioned: 0 }] })
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }))

function mount(search: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/cases/${CASE}/map${search}`]}>
          <Routes><Route path="/cases/:id/map" element={<MapPage />} /></Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  resetRequestsForTest(); localStorage.clear(); canvas.mockClear()
  api.getPhones.mockResolvedValue({ case_id: CASE, total: 3, phones: [phone(A, "Phone 1"), phone(B, "Phone 2"), phone(C, "Phone 3")], case_zone: { name: "UTC", basis: "default", note: null } })
  api.getPhoneMapSummary.mockResolvedValue(summary(642))
  api.getPhoneMapPoints.mockResolvedValue({ case_id: CASE, total: 0, clustered: false, items: [], limits: [] })
  api.getPhoneMapTrajectory.mockResolvedValue({ case_id: CASE, total: 3, untimed: 1, limits: [], items: [
    { point_uid: "1", extraction_id: A, lat: 40, lon: -74, accuracy_m: null, instant: "2023-03-14T09:00:00Z" },
    { point_uid: "2", extraction_id: A, lat: 40.1, lon: -74, accuracy_m: null, instant: "2023-03-14T09:30:00Z" },
    { point_uid: "3", extraction_id: A, lat: 40.2, lon: -74, accuracy_m: null, instant: "2023-03-14T13:30:00Z" },
  ] })
  vi.stubGlobal("fetch", vi.fn((url: string) => (url.startsWith("/api/graph/locations") ? json([]) : json({}))))
})
afterEach(() => vi.unstubAllGlobals())

it("shows no phone layer control while the phone_layers setting is off", async () => {
  mount(`?phones=${A},${B}`)
  await screen.findByTestId("map-canvas")
  expect(screen.queryByTestId("phone-layers")).toBeNull()
  expect(canvas.mock.lastCall?.[0].phoneColours).toBeUndefined()
})

it("lists every phone with its count, asks for only the phones that are on, and says 0 for a phone with nothing", async () => {
  localStorage.setItem("loupe.phone_layers", "on")
  mount(`?phones=${A},${B}`)
  expect(await screen.findByText("412 positions")).toBeTruthy()
  expect(screen.getByText("230 positions")).toBeTruthy()
  expect(screen.getByText("0 positions")).toBeTruthy()
  expect(screen.getByLabelText("Phone 3 on")).not.toBeChecked()
  expect(screen.getByLabelText("Phone 1 on")).toBeChecked()
  await waitFor(() => expect(api.getPhoneMapSummary).toHaveBeenCalledWith(CASE, expect.objectContaining({ phones: [A, B] }), expect.anything()))
  const colours = canvas.mock.lastCall?.[0].phoneColours as Record<string, string>
  expect(new Set(Object.values(colours)).size).toBe(3)
})

it("switching a phone off asks again without it, and the routes state their moves and gaps", async () => {
  localStorage.setItem("loupe.phone_layers", "on")
  mount(`?phones=${A},${B}`)
  fireEvent.click(await screen.findByLabelText("Phone 2 on"))
  await waitFor(() => expect(api.getPhoneMapSummary).toHaveBeenLastCalledWith(CASE, expect.objectContaining({ phones: [A] }), expect.anything()))
  fireEvent.click(screen.getByLabelText("Show routes"))
  await waitFor(() => expect(api.getPhoneMapTrajectory).toHaveBeenCalledWith(CASE, expect.objectContaining({ phones: [A] }), expect.anything()))
  const bar = await screen.findByText(/moves? drawn/)
  expect(bar.textContent).toMatch(/1 move drawn · 1 gap over 2 hours not drawn · 1 positions with no time/)
})
