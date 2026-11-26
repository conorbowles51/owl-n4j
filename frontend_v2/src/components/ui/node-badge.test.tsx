/// <reference types="node" />
import { readFileSync } from "node:fs"
import path from "node:path"
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { contrast, hexToRgb, tripletToRgb, type RGB } from "@/features/phones/lib/contrast"
import { nodeColors } from "@/lib/theme"
import { BADGE_TEXT_SHARE, NodeBadge } from "./node-badge"

/**
 * Type badge labels read 4.5:1 or more (followups 26 Nov: live dark Table scan read 'Financial transaction' 3.65:1 and
 * 'Document' 3.97:1, the raw type colour as text on its own tint).
 */
const css = readFileSync(path.resolve(__dirname, "../../styles/globals.css"), "utf8")
function block(selector: string): Record<string, string> {
  const start = css.indexOf(`  ${selector} {`)
  const body = css.slice(start, css.indexOf("\n  }", start))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}
const mix = (a: RGB, b: RGB, p: number): RGB => a.map((v, i) => v * p + b[i] * (1 - p)) as RGB
const THEMES = { light: block(":root"), dark: { ...block(":root"), ...block(".dark") } }

describe("NodeBadge label contrast", () => {
  it("draws the label as the type colour mixed with the theme text colour, the dot in the pure colour", () => {
    const { container } = render(<NodeBadge type="document" />)
    const badge = container.firstElementChild as HTMLElement
    expect(badge.getAttribute("style")).toContain(`color-mix(in srgb, ${nodeColors.document} ${BADGE_TEXT_SHARE}%`)
  })

  for (const [theme, vars] of Object.entries(THEMES)) {
    it(`every type label reads 4.5:1 or more on its tint over every surface, ${theme}`, () => {
      const fg = tripletToRgb(vars.foreground)
      for (const [type, hex] of Object.entries(nodeColors)) {
        for (const s of ["background", "card", "muted", "popover", "panel", "panel-raised"]) {
          const tint = mix(hexToRgb(hex), tripletToRgb(vars[s]), 0x15 / 255)
          const r = contrast(mix(hexToRgb(hex), fg, BADGE_TEXT_SHARE / 100), tint)
          expect(r, `${type} on ${s} (${theme}) = ${r.toFixed(2)}`).toBeGreaterThanOrEqual(4.5)
        }
      }
    })
  }
})
