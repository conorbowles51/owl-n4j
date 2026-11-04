import { Suspense, type ReactElement } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes, createRoutesFromChildren } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { QueryClient } from "@tanstack/react-query"
import { whenSettled } from "@/features/financial/lib/page-speed"
import { pageChunksPending, resetPageChunks } from "./page-chunks"
import { preloadRoute, preloadRouteIntent, registerRouteTree, routePageFor } from "./route-preload"
import { timedLazy } from "./timed-lazy"
import { appRouteTree, preloadCurrentRoute } from "@/app/route-table"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

afterEach(() => {
  useAuthStore.setState({ isAuthenticated: false, user: null })
  resetPageChunks()
  localStorage.clear()
  window.history.replaceState(null, "", "/")
})

/** A lazy page whose code arrives when the test says so; counts how often its code is asked for. */
function page(text: string) {
  let arrive: () => void = () => {}
  const load = vi.fn(() => new Promise<{ default: () => ReactElement }>((r) => {
    arrive = () => r({ default: () => <div>{text}</div> })
  }))
  return { Page: timedLazy(load), load, arrive: () => arrive() }
}

describe("matching the address against app/routes.tsx", () => {
  const tree = appRouteTree()
  const C = "/cases/c1"

  it("every lazy page in the route table is found at its own address", () => {
    const leaves: { path: string; element: unknown }[] = []
    const walk = (routes: typeof tree, prefix: string) => {
      for (const r of routes) {
        const path = r.index ? prefix : r.path ? `${prefix.replace(/\/$/, "")}/${r.path.replace(/^\//, "")}` : prefix
        if (r.children) walk(r.children, path)
        else if (r.element) leaves.push({ path, element: r.element })
      }
    }
    walk(tree, "")
    const lazyLeaves = leaves.filter((l) => routePageFor([{ path: "*", element: l.element as never }], "/x"))
    expect(lazyLeaves.length).toBeGreaterThanOrEqual(53)
    for (const leaf of lazyLeaves) {
      const address = leaf.path.replace(/\/:[a-zA-Z]+\?/g, "").replace(/:[a-zA-Z]+/g, "p1") || "/"
      const expected = routePageFor([{ path: "*", element: leaf.element as never }], "/x")
      expect(routePageFor(tree, address), address).toBe(expected)
    }
  })

  it("picks the page react-router ranks first where patterns overlap", () => {
    const conversations = routePageFor(tree, `${C}/conversations`)
    expect(conversations).not.toBeNull()
    expect(routePageFor(tree, `${C}/phones/e1/records/conversations`)).toBe(conversations)
    const records = routePageFor(tree, `${C}/phones/e1/records/messages`)
    expect(records).not.toBeNull()
    expect(records).not.toBe(conversations)
    expect(routePageFor(tree, `${C}/phones/e1/records/media/spread`)).not.toBe(routePageFor(tree, `${C}/phones/e1/records/media`))
    expect(routePageFor(tree, `${C}/phones/e1`)).not.toBe(routePageFor(tree, `${C}/phones`))
    expect(routePageFor(tree, `${C}/evidence`)).not.toBe(routePageFor(tree, `${C}/financial`))
  })

  it("starts nothing for the shell's own pages, redirects or unknown addresses", () => {
    for (const address of ["/login", "/cases", "/", C, `${C}/cellebrite`, "/admin/usage", "/nowhere", `${C}/nowhere`]) {
      expect(routePageFor(tree, address), address).toBeNull()
    }
  })

  it("at startup, starts only the page being opened, and only when someone is signed in", async () => {
    window.history.replaceState(null, "", `${C}/evidence`)
    expect(preloadCurrentRoute()).toBe(false) // signed out: the address goes to the sign-in page
    localStorage.setItem("authToken", "t")
    const user = { id: "u1", username: "u" } as never
    useAuthStore.setState({ isAuthenticated: true, user: null })
    expect(preloadCurrentRoute(`${C}/evidence`, "", Promise.resolve(user))).toBe(true)
    expect(pageChunksPending()).toBe(false) // the code waits for the sign-in check (it must not queue behind it)
    // then its first data's module and the data, then the code: the page timer sees the page's code loading
    await waitFor(() => expect(pageChunksPending()).toBe(true), { timeout: 20_000 })
  })
})

describe("each start-up step is off unless its switch is on", () => {
  it("with both steps off, nothing starts and links start nothing", async () => {
    window.history.replaceState(null, "", "/cases/c1/evidence")
    localStorage.setItem("authToken", "t")
    useAuthStore.setState({ isAuthenticated: true, user: null })
    registerRouteTree(() => [])
    expect(preloadCurrentRoute("/cases/c1/evidence", "", Promise.resolve({ id: "u1" } as never), { data: false, code: false })).toBe(false)
    await act(() => new Promise<void>((r) => setTimeout(r, 200)))
    expect(pageChunksPending()).toBe(false)
    expect(preloadRouteIntent("/cases/c1/financial")).toBe(false)
  })

  it("the switches are read from the address like the other switches, and are off by default", async () => {
    const { applySwitchesFromSearch, isSwitchOn } = await import("./ui-switches")
    for (const name of ["open-sign-in-first", "open-data-first", "open-code-first"] as const) {
      expect(isSwitchOn(name)).toBe(false)
      applySwitchesFromSearch(`?${name}=on`)
      expect(isSwitchOn(name)).toBe(true)
      applySwitchesFromSearch(`?${name}=off`)
      expect(isSwitchOn(name)).toBe(false)
    }
  })
})

describe("the code started at startup is the code React renders", () => {
  function app(Page: ReturnType<typeof page>["Page"], at: string) {
    return render(
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/cases/:id/evidence" element={<Suspense fallback={<div>spinner</div>}><Page /></Suspense>} />
        </Routes>
      </MemoryRouter>
    )
  }

  it("is downloaded once, and the page timer waits for it from startup until the page mounts", async () => {
    window.history.replaceState(null, "", "/cases/c1/evidence")
    const { Page, load, arrive } = page("evidence page")
    const routes = createRoutesFromChildren(<Route path="/cases/:id/evidence" element={<Page />} />)
    expect(preloadRoute(routes, "/cases/c1/evidence", "start")).toBe(true)
    expect(load).toHaveBeenCalledTimes(1) // before React has rendered anything
    let settledAt: number | null = null
    void whenSettled(new QueryClient(), { cancelled: false }).then((end) => { settledAt = end })
    await act(() => new Promise<void>((r) => setTimeout(r, 120)))
    expect(settledAt).toBeNull() // the page timer counts the page as loading: its code is on the way
    app(Page, "/cases/c1/evidence")
    await act(() => new Promise<void>((r) => setTimeout(r, 60)))
    expect(settledAt).toBeNull() // code still not here, React is showing the fallback
    const beforeMount = performance.now()
    await act(async () => arrive())
    expect(await screen.findByText("evidence page")).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(1) // React reused the download
    await act(() => new Promise<void>((r) => setTimeout(r, 400)))
    expect(pageChunksPending()).toBe(false)
    expect(settledAt).not.toBeNull()
    expect(settledAt!).toBeGreaterThanOrEqual(beforeMount)
  })

  it("a link pointed at starts the code only, and never holds up the page on screen", async () => {
    window.history.replaceState(null, "", "/cases/c1/table")
    const { Page, load } = page("evidence page")
    registerRouteTree(() => createRoutesFromChildren(<Route path="/cases/:id/evidence" element={<Page />} />))
    expect(preloadRouteIntent("/cases/c1/evidence?tab=x")).toBe(true)
    expect(load).toHaveBeenCalledTimes(1)
    expect(pageChunksPending()).toBe(false)
    window.history.replaceState(null, "", "/cases/c1/evidence")
    expect(pageChunksPending()).toBe(false)
    expect(preloadRouteIntent("/cases/c1/table")).toBe(false)
  })

  it("a failed download is asked for again when React renders the page", async () => {
    let calls = 0
    const load = vi.fn(() => (++calls === 1 ? Promise.reject(new Error("offline")) : Promise.resolve({ default: () => <div>second try</div> })))
    const Page = timedLazy(load)
    Page.preload("intent")
    await new Promise((r) => setTimeout(r, 10))
    render(<Suspense fallback={<div>spinner</div>}><Page /></Suspense>)
    expect(await screen.findByText("second try")).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(2)
  })
})
