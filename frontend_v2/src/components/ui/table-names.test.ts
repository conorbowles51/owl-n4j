import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * A table wider than its panel becomes a focusable scroll region (ui/table.tsx), and a region needs a real name. A
 * table with no aria-label, aria-labelledby or caption falls back to "Table", which tells a screen-reader user
 * nothing about which table they are in (evidence file list at 768 px, 3 Nov). Every use of the shared Table names it.
 */
const SRC = resolve(__dirname, "../..")

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.tsx$/.test(entry) && !/\.(test|stories)\.tsx$/.test(entry) ? [path] : []
  })
}

/** Each `<Table ...>` opening tag in a file that uses the shared table, with whether it carries a name. */
function unnamedTables(): string[] {
  const unnamed: string[] = []
  for (const path of sources(SRC)) {
    const text = readFileSync(path, "utf8")
    if (!/from "@\/components\/ui\/table"/.test(text)) continue
    const hasCaption = /<TableCaption\b/.test(text)
    for (const match of text.matchAll(/<Table(?=[\s>])([^>]*)>/g)) {
      const attrs = match[1]
      if (/aria-label(ledby)?=/.test(attrs) || hasCaption) continue
      const line = text.slice(0, match.index).split("\n").length
      unnamed.push(`${relative(SRC, path)}:${line}`)
    }
  }
  return unnamed
}

describe("shared table names", () => {
  it("finds the tables it audits", () => {
    const count = sources(SRC)
      .map((p) => readFileSync(p, "utf8"))
      .filter((t) => /from "@\/components\/ui\/table"/.test(t))
      .reduce((n, t) => n + [...t.matchAll(/<Table(?=[\s>])/g)].length, 0)
    expect(count).toBeGreaterThanOrEqual(9)
  })

  it("names every table, so an overflowing one is never a region called 'Table'", () => {
    expect(unnamedTables()).toEqual([])
  })
})
