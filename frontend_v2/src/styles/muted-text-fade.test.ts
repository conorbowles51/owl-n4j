/// <reference types="node" />
import fs from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

/**
 * Muted text at full strength reads 4.5:1 or more on every surface (tokens.test.ts); any fade on it drops under
 * that in light (at /80 it is 3.3-3.6:1, at /50 about 2:1). Text and controls keep it at full strength; only an icon
 * drawn from lucide-react, which is not text, may fade.
 */
const src = path.resolve(__dirname, "..")

function files(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return files(p)
    return /\.tsx$/.test(e.name) && !/\.(test|stories)\.tsx$/.test(e.name) ? [p] : []
  })
}

export function fadedMutedText(code: string): { line: number; tag: string }[] {
  const icons = new Set<string>()
  for (const m of code.matchAll(/import\s*\{([^}]*)\}\s*from\s*["']lucide-react["']/g))
    for (const n of m[1].split(",")) icons.add(n.trim().split(/\s+as\s+/).pop() ?? "")
  const out: { line: number; tag: string }[] = []
  for (const m of code.matchAll(/<([A-Za-z][\w.]*)\b(?:[^>"'{}]|"[^"]*"|'[^']*'|\{[^{}]*\})*?(?:["'`]|\{[^{}]*?["'`])[^"'`]*\btext-muted-foreground\/\d+/g)) {
    const tag = m[1]
    // an icon by its own name, or a component passed in as an icon (Icon, Chevron)
    if (icons.has(tag) || /^(Icon|Chevron)$/.test(tag)) continue
    out.push({ line: code.slice(0, m.index).split("\n").length, tag })
  }
  return out
}

describe("muted text is never faded (followups 26 Nov)", () => {
  it("finds a faded paragraph and leaves a faded icon alone", () => {
    const code = 'import { Info } from "lucide-react"\n<Info className="size-8 text-muted-foreground/40" />\n<p className="text-xs text-muted-foreground/70">No file</p>'
    expect(fadedMutedText(code)).toEqual([{ line: 3, tag: "p" }])
  })

  it("no text or control uses text-muted-foreground/NN", () => {
    const gaps = files(src).flatMap((f) => fadedMutedText(fs.readFileSync(f, "utf8")).map((g) => `${path.relative(src, f)}:${g.line} <${g.tag}>`))
    expect(gaps).toEqual([])
  })
})
