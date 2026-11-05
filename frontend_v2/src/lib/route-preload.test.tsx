import { Suspense, type ReactElement } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes, createRoutesFromChildren } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { pageChunksPending, resetPageChunks } from "./page-chunks"
import { preloadRouteIntent, registerRouteTree, routePageFor } from "./route-preload"
import { timedLazy } from "./timed-lazy"
import { appRouteTree } from "@/app/route-table"

afterEach(() => {
  resetPageChunks()
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
})

describe("the code started by a pointed-at link is the code React renders", () => {
  function app(Page: ReturnType<typeof page>["Page"], at: string) {
    return render(
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/cases/:id/evidence" element={<Suspense fallback={<div>spinner</div>}><Page /></Suspense>} />
        </Routes>
      </MemoryRouter>
    )
  }

  it("a link pointed at downloads once: React reuses it, and the page timer counts from when React asks", async () => {
    window.history.replaceState(null, "", "/cases/c1/evidence")
    const { Page, load, arrive } = page("evidence page")
    registerRouteTree(() => createRoutesFromChildren(<Route path="/cases/:id/evidence" element={<Page />} />))
    expect(preloadRouteIntent("/cases/c1/evidence")).toBe(true)
    expect(load).toHaveBeenCalledTimes(1)
    expect(pageChunksPending()).toBe(false)
    app(Page, "/cases/c1/evidence")
    await waitFor(() => expect(pageChunksPending()).toBe(true))
    await act(async () => arrive())
    expect(await screen.findByText("evidence page")).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(pageChunksPending()).toBe(false))
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
    Page.preload()
    await new Promise((r) => setTimeout(r, 10))
    render(<Suspense fallback={<div>spinner</div>}><Page /></Suspense>)
    expect(await screen.findByText("second try")).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(2)
  })
})
