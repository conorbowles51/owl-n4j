import { readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { GLOSSARY, glossaryMarkdown } from "./glossary"
import { PHONE_GUIDES } from "./guide"
import { GUIDE_SCREENS } from "./ui/screen-guide"

// 07 9: the guide and checklist live in docs/user-guide and are served to the Guide button from
// public/docs/phone-guide. The copies must be identical; the glossary page is the glossary list itself.
const REPO = resolve(__dirname, "../../../..")
const doc = (name: string) => readFileSync(resolve(REPO, "docs/user-guide", name), "utf8")
const served = (name: string) => readFileSync(resolve(REPO, "frontend_v2/public/docs/phone-guide", name), "utf8")
const slug = (t: string) => t.toLowerCase().replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-")
const FILES = ["phone-user-guide.md", "phone-team-checklist.md", "phone-glossary.md"]

describe("phone guide documents", () => {
  it("the glossary page is the glossary list", () => {
    if (process.env.WRITE_GLOSSARY) writeFileSync(resolve(REPO, "docs/user-guide/phone-glossary.md"), glossaryMarkdown())
    expect(doc("phone-glossary.md")).toBe(glossaryMarkdown())
  })

  it("every served copy equals its document, and each Guide tab finds its heading", () => {
    for (const name of FILES) expect(served(name), name).toBe(doc(name))
    for (const g of PHONE_GUIDES) {
      const name = g.url.split("/").pop()!
      expect(doc(name).startsWith(g.heading), name).toBe(true)
    }
  })

  it("every Learn more anchor is a heading on the Glossary page", () => {
    const headings = new Set([...doc("phone-glossary.md").matchAll(/^## (.+)$/gm)].map((m) => slug(m[1])))
    for (const e of GLOSSARY) expect(headings.has(e.guide), e.id).toBe(true)
  })

  it("every contents link in the user guide lands on a section", () => {
    const text = doc("phone-user-guide.md")
    const headings = new Set([...text.matchAll(/^## (.+)$/gm)].map((m) => slug(m[1])))
    const links = [...text.matchAll(/\]\(#([a-z0-9-]+)\)/g)].map((m) => m[1])
    expect(links.length).toBeGreaterThan(20)
    for (const l of links) expect(headings.has(l), l).toBe(true)
  })

  it("the checklist has 12 checks or fewer, each with the four results and the honesty rule", () => {
    const text = doc("phone-team-checklist.md")
    const checks = [...text.matchAll(/^## (\d+)\. /gm)]
    expect(checks.length).toBeGreaterThan(0)
    expect(checks.length).toBeLessThanOrEqual(12)
    for (const word of ["**Pass**", "**Fail**", "**Blocked**", "**Not run**"]) expect(text).toContain(word)
    expect(text).toContain("Record what actually happened; do not pass a step just because a button could be clicked.")
    const rows = [...text.matchAll(/^\| (\d+) \|/gm)].map((m) => Number(m[1]))
    expect(rows).toEqual(checks.map((_, i) => i + 1))
  })

  it("every user-guide task states whether it is available in this build", () => {
    const text = doc("phone-user-guide.md")
    const tasks = text.split(/^## /m).filter((s) => /^(Add a phone|First look|Everything with|Read a conversation|The window|Search everything|Who is who|Check the system|Test a statement|Where was|Find deleted|Build the case|Share the review|Export for|Resume and|Compare phones|Explain a finding)/.test(s))
    expect(tasks).toHaveLength(17)
    for (const t of tasks) expect(t, t.split("\n")[0]).toMatch(/\*\*Available:\*\* (not yet|preview only|yes)/)
  })

  it("plain words: no em dashes and no internal names", () => {
    for (const name of FILES) {
      const text = doc(name)
      expect(text, name).not.toContain("—")
      expect(text, name).not.toMatch(/\bJ-\d+\b|cb-[a-z]+|UXD-|Cellebrite|cded78d0/)
    }
  })
})

describe("per-screen Guide links (07 9)", () => {
  it("every screen's link lands on a heading of the served user guide", () => {
    const headings = new Set([...served("phone-user-guide.md").matchAll(/^## (.+)$/gm)].map((m) => slug(m[1])))
    for (const anchor of GUIDE_SCREENS) expect(headings, anchor).toContain(anchor)
  })
})
