import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * The basemap's data is OpenStreetMap (ODbL) served by CARTO, and both licences ask for a visible credit. The style
 * source already carries the credit text; MapLibre shows it only when the attribution control is on. Every map in
 * the app shows it, compact so it costs one small button in the corner.
 */
const SRC = resolve(__dirname, "../..")

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.tsx$/.test(entry) && !/\.(test|stories)\.tsx$/.test(entry) ? [path] : []
  })
}

/** Each map opening tag from react-map-gl, with its file and line. */
function maps(): { where: string; attrs: string }[] {
  const found: { where: string; attrs: string }[] = []
  for (const path of sources(SRC)) {
    const text = readFileSync(path, "utf8")
    const imported = text.match(/import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s+"react-map-gl[^"]*"/)
    if (!imported) continue
    const names = new Set<string>()
    if (imported[1]) names.add(imported[1])
    for (const part of (imported[2] ?? "").split(",")) {
      const m = part.trim().match(/^(?:default|Map)(?:\s+as\s+(\w+))?$/)
      if (m) names.add(m[1] ?? "Map")
    }
    for (const name of names) {
      for (const match of text.matchAll(new RegExp(`<${name}(?=[\\s>])([\\s\\S]*?)>\\s*\\n`, "g"))) {
        const line = text.slice(0, match.index).split("\n").length
        found.push({ where: `${relative(SRC, path)}:${line}`, attrs: match[1] })
      }
    }
  }
  return found
}

describe("map data credit", () => {
  it("finds the app's maps", () => {
    expect(maps().length).toBeGreaterThanOrEqual(2)
  })

  it("never hides the attribution control and shows it compact", () => {
    const hidden = maps()
      .filter(({ attrs }) => !/attributionControl=\{\{\s*compact:\s*true\s*\}\}/.test(attrs))
      .map(({ where }) => where)
    expect(hidden).toEqual([])
  })
})
