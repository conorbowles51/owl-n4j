import { readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

/**
 * amber B (Neil, 1 Nov): the amber-* utilities are drawn in Loupe brand red since the July rebrand, so a warning
 * drawn with them reads as the brand accent and close to an error. Warnings use the status-warning token instead
 * (globals.css; contrast and distance from red in tokens.test.ts). This guard finds amber-* within three lines of a
 * warning signal: an alert role, a warning icon or a "warning" level. Brand-accent amber (page icons, links,
 * highlights) is untouched.
 */
const SRC = path.resolve(__dirname, "..")
const SIGNAL = /role="alert"|AlertTriangle|TriangleAlert|AlertCircle|case "warning"/
/** Reviewed: the line is the non-warning branch beside a warning icon (the normal manual-update icon). */
const ACCENT = new Set(["features/admin/components/PlatformUpdatesPage.tsx: <ServerCog className=\"size-4 text-amber-500\" />"])

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return files(full)
    return /\.tsx$/.test(name) && !/\.(test|stories|browser\.test)\.tsx$/.test(name) ? [full] : []
  })
}

describe("warnings use the warning colour, not brand-red amber", () => {
  it("no amber-* class sits beside an alert role, a warning icon or a warning level", () => {
    const found: string[] = []
    for (const file of files(SRC)) {
      const lines = readFileSync(file, "utf8").split("\n")
      lines.forEach((line, i) => {
        if (!/amber-\d/.test(line)) return
        if (!SIGNAL.test(lines.slice(Math.max(0, i - 3), i + 4).join("\n"))) return
        const key = `${path.relative(SRC, file)}: ${line.trim()}`
        if (!ACCENT.has(key)) found.push(`${path.relative(SRC, file)}:${i + 1}`)
      })
    }
    expect(found).toEqual([])
  })
})
