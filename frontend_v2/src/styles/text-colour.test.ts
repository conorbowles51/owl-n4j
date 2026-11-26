/// <reference types="node" />
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"
import { contrast, hexToRgb, tripletToRgb, type RGB } from "@/features/phones/lib/contrast"

/**
 * Brand red as text reads 4.5:1 or more (followups 26 Nov: live dark scan found 'Learn more' at 3.54:1 and the
 * selected 'Evidence root' at 3.99:1). globals.css redraws text-primary (dark) and text-amber-500 (both themes) as
 * text in a brand shade; this checks that rule exists and that its shade passes on every surface and on a 15% brand
 * tint, the strongest tint a selected row or chip uses behind it.
 */
const css = readFileSync(path.resolve(__dirname, "globals.css"), "utf8")

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`  ${selector} {`)
  const body = css.slice(start, css.indexOf("\n  }", start))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}
const brand: Record<string, string> = {}
for (const m of css.matchAll(/--color-brand-(\d+):\s*(#[0-9A-Fa-f]{6});/g)) brand[m[1]] = m[2]

/** The brand shade a text rule in globals.css gives `selector`, or undefined when no rule does. */
function textShade(selector: RegExp): string | undefined {
  for (const m of css.matchAll(/([^{}]+)\{\s*color:\s*var\(--color-brand-(\d+)\);\s*\}/g))
    if (m[1].split(",").some((s) => selector.test(s.trim()))) return brand[m[2]]
  return undefined
}

const mix = (a: RGB, b: RGB, p: number): RGB => a.map((v, i) => v * p + b[i] * (1 - p)) as RGB
const SURFACES = ["background", "card", "muted", "popover", "panel", "panel-raised", "secondary", "accent", "sidebar"]
const THEMES = {
  light: { vars: block(":root"), rules: [/^\.text-amber-500/] },
  dark: { vars: { ...block(":root"), ...block(".dark") }, rules: [/^\.dark \.text-amber-500/, /^\.dark \.text-primary/] },
}

describe("brand red as text reads 4.5:1 or more", () => {
  for (const [theme, { vars, rules }] of Object.entries(THEMES)) {
    for (const rule of rules) {
      it(`${rule.source} in ${theme}`, () => {
        const shade = textShade(rule)
        expect(shade, `globals.css gives ${rule.source} a brand text shade`).toBeTruthy()
        for (const s of SURFACES) {
          const surface = tripletToRgb(vars[s])
          for (const [name, bg] of [[s, surface], [`${s} + 15% brand`, mix(hexToRgb(brand["500"]), surface, 0.15)]] as const) {
            const r = contrast(hexToRgb(shade!), bg)
            expect(r, `${shade} on ${name} (${theme}) = ${r.toFixed(2)}`).toBeGreaterThanOrEqual(4.5)
          }
        }
      })
    }
  }

  it("an element naming its own dark: text colour keeps it", () => {
    for (const rule of [/^\.text-amber-500/, /^\.dark \.text-amber-500/, /^\.dark \.text-primary/]) {
      const sel = css.split(/[{}]/).flatMap((c) => c.split(",")).map((s) => s.trim()).find((s) => rule.test(s) && /brand|:not/.test(s))
      expect(sel, rule.source).toContain(':not([class*="dark:text-"])')
    }
  })
})
