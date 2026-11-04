import { Suspense, type ReactNode } from "react"
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { act, fireEvent, render } from "@testing-library/react"
import { BrowserRouter, Link, Outlet, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { apiRequestsInFlight, fetchAPI } from "@/lib/api-client"
import { flushPageViews, whenSettled } from "@/features/financial/lib/page-speed"
import { chunkBegan, resetPageChunks } from "./page-chunks"
import { useRouteSpeed } from "./route-speed"
import { timedLazy } from "./timed-lazy"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn(), apiRequestsInFlight: vi.fn() }))

const wait = (ms: number) => act(() => new Promise<void>((r) => setTimeout(r, ms)))

function posted() {
  return vi.mocked(fetchAPI).mock.calls.flatMap(
    ([, options]) => (options as { body: { views: { page: string; method: string; ms: number }[] } }).body.views)
}

/** A route page whose code takes `chunk` to arrive, and whose data is asked for only once it has mounted. */
function slowPage() {
  let arrive: () => void = () => {}
  let answer: (value: number) => void = () => {}
  function MapPage() {
    const { data } = useQuery({ queryKey: ["locations"], queryFn: () => new Promise<number>((r) => { answer = r }) })
    return <div>{data ?? "loading"}</div>
  }
  const Page = timedLazy(() => new Promise<{ default: typeof MapPage }>((r) => { arrive = () => r({ default: MapPage }) }))
  return { Page, arrive: () => arrive(), answer: (v: number) => answer(v) }
}

function Layout() {
  useRouteSpeed()
  return <Outlet />
}

function TablePage() {
  return <Link to="/cases/c1/map">map</Link>
}

function App({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/cases/:id/table" element={<TablePage />} />
            <Route path="/cases/:id/map" element={<Suspense fallback={<div>spinner</div>}>{children}</Suspense>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockResolvedValue({ accepted: 1 })
  vi.mocked(apiRequestsInFlight).mockReturnValue(0)
  resetPageChunks()
})
afterEach(() => {
  flushPageViews()
  window.history.replaceState(null, "", "/")
})

describe("route timer and lazy pages", () => {
  it("a page opened at its address is not on screen until the data it asks for after its code arrives has returned", async () => {
    window.history.replaceState(null, "", "/cases/c1/map")
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { Page, arrive, answer } = slowPage()
    const app = render(<App client={client}><Page /></App>)
    await wait(60) // the spinner is up, nothing is fetching yet
    await act(async () => arrive())
    await wait(60) // the page has asked for its data
    await act(async () => answer(7))
    await wait(80)
    app.unmount()
    flushPageViews()
    const map = posted().filter((v) => v.page === "case/map")
    expect(map.map((v) => v.method)).toEqual(["VIEW"])
    expect(map[0].ms).toBeGreaterThanOrEqual(115) // code (60) + data (60)
  })

  it("a page opened inside the app is timed from the person's click, through its code and its data", async () => {
    window.history.replaceState(null, "", "/cases/c1/table")
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { Page, arrive, answer } = slowPage()
    const app = render(<App client={client}><Page /></App>)
    await wait(40)
    await act(async () => fireEvent.click(app.getByText("map")))
    await wait(60) // the table stays on screen while the map's code arrives
    await act(async () => arrive())
    await wait(60)
    await act(async () => answer(7))
    await wait(80)
    app.unmount()
    flushPageViews()
    const map = posted().filter((v) => v.page === "case/map")
    expect(map.map((v) => v.method)).toEqual(["VIEW"])
    expect(map[0].ms).toBeGreaterThanOrEqual(115)
  })

  it("code still on its way for an address already left does not hold up the page now open", async () => {
    window.history.replaceState(null, "", "/cases/c1/map")
    chunkBegan() // never arrives
    window.history.replaceState(null, "", "/cases/c1/table")
    const client = new QueryClient()
    const settled = await whenSettled(client, { cancelled: false })
    expect(typeof settled).toBe("number")
  })
})
