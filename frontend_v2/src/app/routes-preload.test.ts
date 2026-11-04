/**
 * The startup preload (main.tsx -> preloadRoutePage) knows the lazy page of every address the routes open, and finds
 * the page an address renders. followups m11041509594207: a fresh /cases/<id>/evidence ran shell -> page code -> data
 * in series; the preload starts the page code beside the shell.
 */
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it, vi } from "vitest"

const here = dirname(fileURLToPath(import.meta.url))

describe("route page preload", () => {
  it("has one entry for every lazy page the routes render, at the same address", async () => {
    const source = readFileSync(resolve(here, "routes.tsx"), "utf8")
    const routes = source.slice(source.indexOf("export function AppRoutes"))
    const want: string[] = []
    let prefix = ""
    for (const line of routes.split("\n")) {
      const layout = line.match(/<Route path="(\/cases\/:id|\/admin)" element=\{<(?:CaseLayout|AdminLayout) \/>\}>/)
      if (layout) { prefix = layout[1]; continue }
      if (/^\s*<\/Route>/.test(line) && prefix) { prefix = ""; continue }
      const m = line.match(/<Route (?:path="([^"]+)"|index) element=\{<LazyPage><(\w+) \/><\/LazyPage>\}/)
      if (m) want.push(`${m[1]?.startsWith("/") ? m[1] : prefix + (m[1] ? "/" + m[1] : "")} ${m[2]}`)
    }
    const table = [...readFileSync(resolve(here, "route-pages.ts"), "utf8").matchAll(/\{ path: "([^"]+)", page: (\w+) \}/g)].map((m) => `${m[1]} ${m[2]}`)
    expect(want.length).toBeGreaterThan(50)
    for (const w of want) expect(table).toContain(w)
  })

  it("starts the download of the page the address opens, once per address", async () => {
    const { PAGE_CHUNK_ROUTES, preloadRoutePage } = await import("./route-pages")
    const pages = [...new Set(PAGE_CHUNK_ROUTES.map((r) => r.page))]
    const spies = pages.map((page) => vi.spyOn(page, "preload").mockResolvedValue({}))
    expect(preloadRoutePage("/cases/c1/evidence")).toBe("/cases/:id/evidence")
    expect(preloadRoutePage("/cases/c1/phones/e1/records/media")).toBe("/cases/:id/phones/:extraction/records/media")
    expect(preloadRoutePage("/cases/c1/phones/e1/records/calls")).toBe("/cases/:id/phones/:extraction/records/:recordType")
    expect(preloadRoutePage("/cases/c1")).toBe("/cases/:id")
    expect(preloadRoutePage("/admin")).toBe("/admin")
    expect(preloadRoutePage("/cases")).toBeNull() // the case list is in the shell
    expect(preloadRoutePage("/login")).toBeNull()
    expect(spies.filter((s) => s.mock.calls.length > 0).length).toBe(5)
    expect(spies.every((s) => s.mock.calls.length <= 1)).toBe(true)
  })
})
