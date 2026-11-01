import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"
import { contrast, hexToRgb, tripletToRgb } from "../lib/contrast"
import { PHONE_PALETTE, PHONE_SHAPES } from "../lib/phone-palette"

const css = readFileSync(path.resolve(__dirname, "../../../styles/globals.css"), "utf8")

function block(selector: ":root" | ".dark"): Record<string, string> {
  const start = css.indexOf(`  ${selector} {`)
  const body = css.slice(start, css.indexOf("\n  }", start))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/--([a-z-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}

const THEMES = { light: block(":root"), dark: { ...block(":root"), ...block(".dark") } }
const SURFACES = ["background", "card", "muted", "popover", "panel"]
const STATUSES = ["status-review", "status-model", "status-deleted", "status-error"]

describe("phone status tokens (07 4.2 item 3)", () => {
  for (const [theme, vars] of Object.entries(THEMES)) {
    for (const status of STATUSES) {
      it(`${status} is 4.5:1 or more on every surface and its soft fill, ${theme}`, () => {
        expect(vars[status], `${status} defined in ${theme}`).toBeTruthy()
        for (const surface of [...SURFACES, `${status}-soft`]) {
          const ratio = contrast(tripletToRgb(vars[status]), tripletToRgb(vars[surface]))
          expect(ratio, `${status} on ${surface} (${theme}) = ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5)
        }
      })
    }
  }
  it("each token is mapped for Tailwind", () => {
    for (const status of STATUSES) {
      expect(css).toContain(`--color-${status}: hsl(var(--${status}));`)
      expect(css).toContain(`--color-${status}-soft: hsl(var(--${status}-soft));`)
    }
  })
})

describe("phone palette (07 4.11)", () => {
  it("has 10 distinct hues and 10 distinct shapes", () => {
    expect(new Set(PHONE_PALETTE.light).size).toBe(10)
    expect(new Set(PHONE_PALETTE.dark).size).toBe(10)
    expect(new Set(PHONE_SHAPES).size).toBe(10)
  })
  for (const theme of ["light", "dark"] as const) {
    it(`every hue is 3:1 or more against the page surfaces, ${theme}`, () => {
      for (const hex of PHONE_PALETTE[theme]) {
        for (const surface of ["background", "card", "muted"]) {
          const ratio = contrast(hexToRgb(hex), tripletToRgb(THEMES[theme][surface]))
          expect(ratio, `${hex} on ${surface} (${theme})`).toBeGreaterThanOrEqual(3)
        }
      }
    })
  }
})
