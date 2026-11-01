/** WCAG 2.2 relative luminance and contrast ratio, for the token and palette checks (07 4.2 item 3, 4.11). */

export type RGB = [number, number, number]

export function hslToRgb(h: number, s: number, l: number): RGB {
  const sat = s / 100
  const light = l / 100
  const k = (n: number) => (n + h / 30) % 12
  const a = sat * Math.min(light, 1 - light)
  const f = (n: number) => light - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
  return [f(0), f(8), f(4)]
}

export function hexToRgb(hex: string): RGB {
  const v = hex.replace("#", "")
  return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255) as RGB
}

/** "30 90% 30%" (the theme's HSL triplet form) to RGB. */
export function tripletToRgb(triplet: string): RGB {
  const [h, s, l] = triplet.replace(/%/g, "").trim().split(/\s+/).map(Number)
  return hslToRgb(h, s, l)
}

export function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

export function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
