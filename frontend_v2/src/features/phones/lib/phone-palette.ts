/**
 * The phone palette (07 4.11): 10 colour-blind-safe hues, always shown with the phone's label and, on the map,
 * with a marker shape, so colour is never the only cue. Hues are the Okabe-Ito set plus two from Paul Tol's set;
 * each is adjusted per theme to 3:1 or more against the page, card and muted surfaces (WCAG 1.4.11, graphics),
 * checked in phone-palette.test.ts.
 */

export const PHONE_SHAPES = [
  "circle", "square", "triangle", "diamond", "star", "cross", "hexagon", "pentagon", "triangle-down", "ring",
] as const
export type PhoneShape = (typeof PHONE_SHAPES)[number]

export const PHONE_PALETTE = {
  light: ["#0072B2", "#D55E00", "#00946C", "#C46398", "#AE7800", "#1A8AC9", "#8E850B", "#882255", "#3A9082", "#86862D"],
  dark: ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#C13079", "#44AA99", "#999933"],
} as const

export const PHONE_COLOUR_NAMES = [
  "blue", "vermillion", "green", "pink", "orange", "sky", "olive", "wine", "teal", "khaki",
] as const

export interface PhoneMark {
  index: number
  light: string
  dark: string
  shape: PhoneShape
  colourName: string
}

/** The mark for the n-th phone in a case (stable order: by extraction date, then label). Wraps after 10. */
export function phoneMark(index: number): PhoneMark {
  const i = ((index % 10) + 10) % 10
  return {
    index: i,
    light: PHONE_PALETTE.light[i],
    dark: PHONE_PALETTE.dark[i],
    shape: PHONE_SHAPES[i],
    colourName: PHONE_COLOUR_NAMES[i],
  }
}

/** SVG path data for each marker shape in a 16x16 box. */
export const SHAPE_PATHS: Record<PhoneShape, string> = {
  circle: "M8 2a6 6 0 1 0 0 12A6 6 0 1 0 8 2z",
  square: "M2.5 2.5h11v11h-11z",
  triangle: "M8 1.5l6.5 12h-13z",
  diamond: "M8 1l7 7-7 7-7-7z",
  star: "M8 1l1.9 4.6 4.9.4-3.7 3.2 1.1 4.8L8 11.5 3.8 14l1.1-4.8L1.2 6l4.9-.4z",
  cross: "M5.5 1.5h5v4h4v5h-4v4h-5v-4h-4v-5h4z",
  hexagon: "M4.5 2h7L15 8l-3.5 6h-7L1 8z",
  pentagon: "M8 1.5l6.5 4.7-2.5 7.8H4l-2.5-7.8z",
  "triangle-down": "M1.5 2.5h13L8 14.5z",
  ring: "M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 1 0 0-13zm0 3a3.5 3.5 0 1 1 0 7 3.5 3.5 0 1 1 0-7z",
}
