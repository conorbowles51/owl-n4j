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

  it("the hand-picked light warning amber (#fdf6dd) never pairs with a brand-red amber-* class in dark mode", () => {
    // Model-reading notes ("Read by Claude · not confirmed") draw light amber from fixed hex values; their dark:
    // classes must use status-warning, or dark mode shows them in Loupe red (lx-style, live 2 Nov).
    const found: string[] = []
    for (const file of files(SRC)) {
      readFileSync(file, "utf8").split("\n").forEach((line, i) => {
        if (/#fdf6dd/i.test(line) && /amber-\d/.test(line)) found.push(`${path.relative(SRC, file)}:${i + 1}`)
      })
    }
    expect(found).toEqual([])
  })

  it("warning tones in tone helpers (attention band 1, reconciliation 'under') use status-warning", () => {
    const tone = (rel: string, marker: RegExp) => {
      const lines = readFileSync(path.join(SRC, rel), "utf8").split("\n")
      const i = lines.findIndex((l) => marker.test(l))
      expect(i, `${rel} ${marker}`).toBeGreaterThanOrEqual(0)
      return lines.slice(i, i + 2).join("\n")
    }
    expect(tone("features/workspace/components/CanonicalWorkspaceOverview.tsx", /priorityBand === 1/)).not.toMatch(/amber-\d/)
    expect(tone("features/cellebrite/components/overview/OverviewTab.tsx", /status === "under"/)).not.toMatch(/amber-\d/)
  })
})
