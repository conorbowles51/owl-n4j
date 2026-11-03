import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * Loading a Loupe page asks no third party for anything. The typefaces are served from this server (styles/fonts.css);
 * fetching them from Google Fonts told Google which address uses Loupe and when, on every page load.
 */
const ROOT = resolve(__dirname, "..")
const read = (path: string) => readFileSync(resolve(ROOT, path), "utf8")

describe("self-hosted fonts", () => {
  it("index.html loads nothing from another host", () => {
    const html = read("index.html")
    const external = [...html.matchAll(/(?:href|src)="(https?:)?\/\/[^"]+"/g)].map((m) => m[0])
    expect(external).toEqual([])
  })

  it("every family and weight the app styles with has a local face, and every file exists", () => {
    const css = read("src/styles/fonts.css")
    expect(read("src/styles/globals.css")).toMatch(/@import "\.\/fonts\.css";/)
    const faces = [...css.matchAll(/@font-face \{([^}]*)\}/g)].map((m) => m[1])
    const have = new Set(
      faces.map((f) => `${f.match(/font-family: '([^']+)'/)![1]} ${f.match(/font-weight: (\d+)/)![1]}`)
    )
    const want = [
      "IBM Plex Sans 400", "IBM Plex Sans 500", "IBM Plex Sans 600",
      "IBM Plex Mono 400", "IBM Plex Mono 500",
      "Space Grotesk 500", "Space Grotesk 600", "Space Grotesk 700",
    ]
    expect(want.filter((w) => !have.has(w))).toEqual([])
    for (const face of faces) {
      expect(face).not.toMatch(/https?:/)
      const file = face.match(/url\(([^)]+)\)/)![1]
      expect(existsSync(resolve(ROOT, "src/styles", file)), file).toBe(true)
    }
  })
})
