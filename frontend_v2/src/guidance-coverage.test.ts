/// <reference types="node" />
import fs from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"
import { guideTargets, headingSlugs, iconGaps, scanAll } from "../scripts/guidance-coverage.js"
import { TOURS, tourArea, type TourArea } from "@/features/guidance/tours"
import { AREA_GUIDE, GUIDES } from "@/features/guidance/guides"
import { termAnchor } from "@/components/ui/glossary"

/**
 * Guidance coverage (lx-guidecover G). A new screen or control without guidance fails here:
 *   1. every icon-only control has an accessible name and a tooltip that keyboard focus opens
 *   2. every case address has a tour
 *   3. every control a tour points at (data-guide) exists in the code
 *   4. every glossary link lands on a heading, and every area's guide exists
 */
const root = path.resolve(__dirname, "..")
const src = path.join(root, "src")
const scanned = scanAll(src)

/** Icon-only controls left without a tooltip on purpose, each with the reason. Keep this list short. */
const ALLOW: Record<string, string> = {}

describe("guidance coverage", () => {
  it("every icon-only control has a name and a tooltip", () => {
    const gaps = iconGaps(scanned, ALLOW).map((c) => `${c.file}:${c.line} <${c.tag}> ${c.hasName ? "" : "no name; "}${c.hasTooltip ? "" : "no tooltip"}`)
    expect(gaps).toEqual([])
    for (const why of Object.values(ALLOW)) expect(why.length).toBeGreaterThan(20)
  })

  it("every case address has a tour", () => {
    const routes = fs.readFileSync(path.join(src, "app/routes.tsx"), "utf8")
    const start = routes.indexOf('<Route path="/cases/:id"')
    // the case's own routes: after the case layout's opening tag, up to its closing one
    const block = routes.slice(routes.indexOf(">", start) + 1, routes.indexOf("</Route>", start))
    const paths = [...block.matchAll(/<Route (index )?(?:path="([^"]*)" )?element=\{(<Navigate)?/g)]
      .filter((m) => !m[3])
      .map((m) => (m[1] ? "" : m[2]))
      .filter((p): p is string => p !== undefined)
    expect(paths.length).toBeGreaterThan(30)
    const missing = paths.filter((p) => !tourArea(`/cases/c1/${p.replace(/:[a-zA-Z]+\?/g, "").replace(/:[a-zA-Z]+/g, "x")}`))
    expect(missing).toEqual([])
  })

  it("every area has a tour of 3 to 6 steps and a guide", () => {
    for (const [area, tour] of Object.entries(TOURS)) {
      expect(tour.area).toBe(area)
      expect(tour.steps.length).toBeGreaterThanOrEqual(3)
      expect(tour.steps.length).toBeLessThanOrEqual(6)
      expect(AREA_GUIDE[area as TourArea]).toBeTruthy()
    }
  })

  it("every control a tour points at exists in the code", () => {
    const anchors = guideTargets(scanned)
    const named = new Set<string>()
    for (const tour of Object.values(TOURS))
      for (const sel of [...tour.steps.flatMap((s) => s.targets), tour.panel ?? ""])
        for (const m of sel.matchAll(/\[data-guide="([^"]+)"\]/g)) named.add(m[1])
    // the step history strip and the Guide menu are drawn with data-guide set by a prop, not a literal
    const missing = [...named].filter((g) => !anchors.has(g))
    expect(missing).toEqual([])
  })

  it("every glossary link lands on a heading, and every guide file exists with its first line", () => {
    const docs = path.join(root, "public/docs")
    const glossary = fs.readFileSync(path.join(docs, "glossary.md"), "utf8")
    expect(glossary.startsWith("# Glossary")).toBe(true)
    const headings = new Set([...glossary.matchAll(/^## (.+)$/gm)].map((m) => termAnchor(m[1])))
    const links = scanned.flatMap((f) => f.terms.map((t) => ({ where: `${f.file}:${t.line}`, term: t.term })))
    expect(links.length).toBeGreaterThan(20)
    const broken = links.filter((l) => !headings.has(termAnchor(l.term))).map((l) => `${l.where} "${l.term}"`)
    expect(broken).toEqual([])
    expect(headingSlugs(glossary).size).toBeGreaterThan(30)
    for (const g of Object.values(GUIDES)) {
      const file = path.join(docs, g.url.replace(/^.*?docs\//, ""))
      expect(fs.existsSync(file), file).toBe(true)
      expect(fs.readFileSync(file, "utf8").startsWith(g.heading), file).toBe(true)
    }
  })
})
