/**
 * Scale claims. Every entry in `verified` is directly observed in production use and
 * may appear as fact on the page. Every entry in `retired` is a figure that previously
 * appeared on the site and is NOT supported — these must never reappear.
 *
 * See docs/superpowers/specs/2026-08-04-landing-page-redesign-design.md §3.
 */

export const verified = {
  entitiesInOneMatter: 30_000,
  relationshipsInOneMatter: 90_000,
  concurrentMattersAtThatScale: 5,
  phoneExtractionsInOneCase: 5,
  ingestWindowHours: "12–24",
} as const

/**
 * Prose forms of the verified figures. Components import these rather than
 * formatting numbers themselves, so the page can never drift from §3.
 */
export const scaleLine =
  "One matter: thirty thousand entities, ninety thousand relationships, every fact citing its page."

export const scaleComparison =
  "One matter we have run holds thirty thousand entities and ninety thousand relationships. Five matters that size sat on a single instance at once."

/** Substrings that must not appear in any source file under src/. */
export const retired: readonly string[] = [
  "two hundred thousand documents",
  "200,000 documents",
  "five hundred hours",
  "Ten phones",
  "ten phones",
]
