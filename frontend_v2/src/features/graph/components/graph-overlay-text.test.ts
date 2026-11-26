/// <reference types="node" />
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"
import { contrast, hexToRgb, type RGB } from "@/features/phones/lib/contrast"
import { getCanvasColors } from "@/lib/theme"

/**
 * The Graph's overlay labels (item and link counter, the drag hint) read 4.5:1 or more in both themes (followups
 * 26 Nov: the light counter '1,212 items · 3,268 links' read 4.07:1 live, slate-500 on the slate-100/90 overlay).
 * Each overlay names its slate text and background shades; this composites the background over the canvas colour
 * and checks the text against it.
 */
const css = readFileSync(path.resolve(__dirname, "../../../styles/globals.css"), "utf8")
const slate: Record<string, RGB> = {}
for (const m of css.matchAll(/--color-slate-(\d+):\s*(#[0-9A-Fa-f]{6});/g)) slate[m[1]] = hexToRgb(m[2])
const mix = (a: RGB, b: RGB, p: number): RGB => a.map((v, i) => v * p + b[i] * (1 - p)) as RGB

const FILES = ["GraphCanvas.tsx", "GraphCanvas3D.tsx"]
const overlays = FILES.flatMap((f) =>
  [...readFileSync(path.resolve(__dirname, f), "utf8").matchAll(/className="([^"]*bg-slate-100\/90[^"]*)"/g)].map(
    (m) => ({ file: f, cls: m[1].split(/\s+/) }),
  ),
)

function pick(cls: string[], re: RegExp): RegExpMatchArray {
  const hit = cls.map((c) => c.match(re)).find(Boolean)
  expect(hit, `${re.source} in ${cls.join(" ")}`).toBeTruthy()
  return hit!
}

describe("Graph overlay labels read 4.5:1 or more", () => {
  it("finds the overlays", () => expect(overlays.length).toBeGreaterThanOrEqual(3))
  for (const [theme, dark] of [["light", false], ["dark", true]] as const) {
    it(`in the ${theme} theme`, () => {
      const canvas = hexToRgb(getCanvasColors(dark).background)
      const p = dark ? "dark:" : ""
      for (const { file, cls } of overlays) {
        const bg = pick(cls, new RegExp(`^${p}bg-slate-(\\d+)/(\\d+)$`))
        const fg = pick(cls, new RegExp(`^${p}text-slate-(\\d+)$`))
        const r = contrast(slate[fg[1]], mix(slate[bg[1]], canvas, Number(bg[2]) / 100))
        expect(r, `${file} text-slate-${fg[1]} on bg-slate-${bg[1]}/${bg[2]} (${theme}) = ${r.toFixed(2)}`).toBeGreaterThanOrEqual(4.5)
      }
    })
  }
})
