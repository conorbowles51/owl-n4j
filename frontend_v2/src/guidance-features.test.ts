/// <reference types="node" />
import fs from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"
import { headingSlugs, scanAll } from "../scripts/guidance-coverage.js"
import { FEATURES } from "@/features/guidance/feature-list"
import { GUIDES } from "@/features/guidance/guides"
import { TOURS } from "@/features/guidance/tours"
import { termAnchor } from "@/components/ui/glossary"

/**
 * Every feature in features/guidance/feature-list.ts has its guidance (lx-guidecover, Neil 23 Nov): a guide section,
 * the same section in the user documentation in docs/user-guide, a tour step or a next step, a tooltip or Learn more
 * on its screen (or a written reason it has no control), and glossary terms that exist.
 */
const root = path.resolve(__dirname, "..")
const repo = path.resolve(root, "..")
const src = path.join(root, "src")
const publicDocs = path.join(root, "public/docs")
const slug = (h: string) => [...headingSlugs(`## ${h}`)][0]

/** The guide file the app serves, and its copy in the user documentation. */
function guideFiles(id: keyof typeof GUIDES): { served: string; docs: string } {
  const served = path.join(publicDocs, GUIDES[id].url.replace(/^.*?docs\//, ""))
  if (id === "financial") return { served, docs: path.join(repo, "docs/user-guide/financial-user-guide.md") }
  if (id === "phones") return { served, docs: path.join(repo, "docs/user-guide/phone-user-guide.md") }
  return { served, docs: path.join(repo, `docs/user-guide/guides/${id}.md`) }
}

describe("every feature has its guidance", () => {
  const scanned = new Map(scanAll(src).map((f) => [f.file, f]))
  const glossary = new Set([...fs.readFileSync(path.join(publicDocs, "glossary.md"), "utf8").matchAll(/^## (.+)$/gm)].map((m) => termAnchor(m[1])))
  const nextKinds = new Set([...fs.readFileSync(path.join(src, "features/guidance/next-steps.ts"), "utf8").matchAll(/\{ kind: "([a-z-]+)"/g)].map((m) => m[1]))

  it("lists every feature once", () => {
    expect(FEATURES.length).toBeGreaterThan(60)
    const ids = FEATURES.map((f) => f.id)
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
  })

  it("each feature has a guide section, and the user documentation has it too", () => {
    const missing: string[] = []
    for (const f of FEATURES) {
      const { served, docs } = guideFiles(f.guide.id)
      for (const file of [served, docs]) {
        const text = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : ""
        if (!headingSlugs(text).has(slug(f.guide.heading))) missing.push(`${f.id}: no "${f.guide.heading}" in ${path.relative(repo, file)}`)
      }
    }
    expect(missing).toEqual([])
  })

  it("each feature has a tour step or a next step", () => {
    const missing: string[] = []
    for (const f of FEATURES) {
      if (!f.tour && !f.next) missing.push(`${f.id}: no tour step and no next step`)
      if (f.tour && !TOURS[f.tour.area]?.steps.some((s) => s.title === f.tour!.step)) missing.push(`${f.id}: no step "${f.tour.step}" in the ${f.tour.area} tour`)
      if (f.next && !nextKinds.has(f.next)) missing.push(`${f.id}: no next step "${f.next}"`)
    }
    expect(missing).toEqual([])
  })

  it("each feature's screen has a tooltip or Learn more, or says why it has no control", () => {
    const missing: string[] = []
    for (const f of FEATURES) {
      if (f.noControl) {
        if (f.noControl.length < 30 || f.files?.length) missing.push(`${f.id}: noControl needs a reason and no files`)
        continue
      }
      if (!f.files?.length) { missing.push(`${f.id}: no files`); continue }
      for (const file of f.files) if (!scanned.has(file)) missing.push(`${f.id}: ${file} is not a screen file`)
      const tipped = f.files.some((file) => {
        const s = scanned.get(file)
        // an InfoTip is a tooltip of its own (an ⓘ that hover, focus or a click opens)
        const infoTip = /<InfoTip\b/.test(fs.readFileSync(path.join(src, file), "utf8"))
        return !!s && (infoTip || s.terms.length > 0 || s.controls.some((c: { hasTooltip: boolean }) => c.hasTooltip))
      })
      if (!tipped) missing.push(`${f.id}: no tooltip or Learn more in ${f.files.join(", ")}`)
    }
    expect(missing).toEqual([])
  })

  it("each glossary term a feature names is in the glossary", () => {
    const missing = FEATURES.flatMap((f) => f.terms.filter((t) => !glossary.has(termAnchor(t))).map((t) => `${f.id}: "${t}"`))
    expect(missing).toEqual([])
  })

  it("the guides the app serves are the user documentation in docs/user-guide, word for word", () => {
    const pairs: [string, string][] = [
      ["glossary.md", "glossary.md"],
      ["phone-user-guide.md", "phone-guide/phone-user-guide.md"],
      ...fs.readdirSync(path.join(repo, "docs/user-guide/guides")).map((f): [string, string] => [`guides/${f}`, `guides/${f}`]),
    ]
    expect(pairs.length).toBeGreaterThan(10)
    const differ = pairs
      .filter(([d, p]) => fs.readFileSync(path.join(repo, "docs/user-guide", d), "utf8") !== fs.readFileSync(path.join(publicDocs, p), "utf8"))
      .map(([d]) => `docs/user-guide/${d} differs from the app's copy: run node scripts/sync_user_guides.cjs`)
    expect(differ).toEqual([])
    for (const g of Object.keys(GUIDES).filter((id) => id !== "financial" && id !== "phones"))
      expect(fs.existsSync(path.join(repo, `docs/user-guide/guides/${g}.md`)), g).toBe(true)
  })
})
