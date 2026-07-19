/**
 * Single source of truth for the location confidence vocabulary.
 *
 * Tiers High / Medium / Low come directly from the geocoder's confidence
 * values; Manual is a distinct tier for investigator-placed or corrected
 * locations and always outranks the automatic tiers. The same labels are
 * used in the marker popup, the map legend, the confidence filter and the
 * entity details panel.
 */

export type ConfidenceTier = "manual" | "high" | "medium" | "low" | "unverified"

export const CONFIDENCE_TIERS: ConfidenceTier[] = [
  "manual",
  "high",
  "medium",
  "low",
  "unverified",
]

export const CONFIDENCE_TIER_LABELS: Record<ConfidenceTier, string> = {
  manual: "Manual",
  high: "High",
  medium: "Medium",
  low: "Low",
  unverified: "Unverified",
}

/** Badge variants (components/ui/badge) per tier. */
export const CONFIDENCE_TIER_BADGE_VARIANTS: Record<
  ConfidenceTier,
  "info" | "success" | "warning" | "danger" | "slate"
> = {
  manual: "info",
  high: "success",
  medium: "warning",
  low: "danger",
  unverified: "slate",
}

/** Swatch colors for the map legend. */
export const CONFIDENCE_TIER_COLORS: Record<ConfidenceTier, string> = {
  manual: "#3b82f6",
  high: "#10b981",
  medium: "#eab308",
  low: "#ef4444",
  unverified: "#64748b",
}

/** Fields that, when in manual_fields, mean an investigator placed/corrected the location. */
const MANUAL_LOCATION_FIELDS = [
  "latitude",
  "longitude",
  "location_name",
  "location_formatted",
]

export interface LocationConfidenceInput {
  geocoding_confidence?: string | null
  geocoding_confidence_score?: number | null
  geocoding_status?: string | null
  location_specificity?: string | null
  manual_fields?: string[] | null
}

export function isManuallyPlaced(input: LocationConfidenceInput): boolean {
  const manual = input.manual_fields
  if (!Array.isArray(manual)) return false
  return MANUAL_LOCATION_FIELDS.some((f) => manual.includes(f))
}

export function getConfidenceTier(input: LocationConfidenceInput): ConfidenceTier {
  if (isManuallyPlaced(input)) return "manual"
  const confidence = input.geocoding_confidence?.toLowerCase()
  if (confidence === "high" || confidence === "medium" || confidence === "low") {
    return confidence
  }
  return "unverified"
}

/**
 * Whether a location belongs in the needs-review queue: low-confidence
 * geocodes, anything flagged ambiguous/unverified/failed at ingestion, and
 * locations whose address specificity was never resolved (too vague to trust).
 * Manually placed locations never need review.
 */
export function needsReview(input: LocationConfidenceInput): boolean {
  if (isManuallyPlaced(input)) return false
  const status = input.geocoding_status?.toLowerCase()
  if (status === "ambiguous" || status === "unverified" || status === "failed") {
    return true
  }
  // Explicitly classified as unknown at ingestion — too vague to trust.
  // Absent specificity (legacy data) is not treated as ambiguous.
  if (input.location_specificity?.toLowerCase() === "unknown") return true
  return getConfidenceTier(input) === "low"
}

/** Human-readable reason a location is in the review queue. */
export function reviewReason(input: LocationConfidenceInput): string {
  const status = input.geocoding_status?.toLowerCase()
  if (status === "ambiguous") return "Ambiguous at ingestion"
  if (status === "unverified") return "Unverified at ingestion"
  if (status === "failed") return "Geocoding failed"
  if (getConfidenceTier(input) === "low") return "Low geocoding confidence"
  return "Unknown address specificity"
}

// ---------------------------------------------------------------------------
// Continuous confidence scale (0–100%)
// ---------------------------------------------------------------------------

/**
 * Representative percentages for tiers with no numeric geocoder score
 * (legacy data, manual placements). Aligned with the geocoder's bucket
 * thresholds: score > 0.7 → High, > 0.4 → Medium, else Low.
 */
const TIER_DEFAULT_PERCENT: Record<ConfidenceTier, number> = {
  manual: 100,
  high: 85,
  medium: 55,
  low: 20,
  unverified: 0,
}

/**
 * Normalize a location's confidence to a 0–100 scale. Manual placements are
 * always 100. When the geocoder's raw score (0–1) is available it is used
 * directly; otherwise the tier's representative percentage is used.
 */
export function confidencePercent(input: LocationConfidenceInput): number {
  const tier = getConfidenceTier(input)
  if (tier === "manual") return 100
  const score = input.geocoding_confidence_score
  if (typeof score === "number" && Number.isFinite(score)) {
    return Math.round(Math.min(1, Math.max(0, score)) * 100)
  }
  return TIER_DEFAULT_PERCENT[tier]
}

// ---------------------------------------------------------------------------
// Location specificity (DKT-934 taxonomy)
// ---------------------------------------------------------------------------

/** Ordered least → most specific. */
export const LOCATION_SPECIFICITY_LEVELS = [
  "unknown",
  "continent",
  "country",
  "region",
  "city",
  "district",
  "street",
  "exact_address",
] as const

export type LocationSpecificity = (typeof LOCATION_SPECIFICITY_LEVELS)[number]

export const LOCATION_SPECIFICITY_LABELS: Record<LocationSpecificity, string> = {
  unknown: "Unknown",
  continent: "Continent",
  country: "Country",
  region: "Region",
  city: "City",
  district: "District",
  street: "Street",
  exact_address: "Exact address",
}

export function getLocationSpecificity(
  input: LocationConfidenceInput
): LocationSpecificity {
  const value = input.location_specificity?.toLowerCase()
  return (LOCATION_SPECIFICITY_LEVELS as readonly string[]).includes(value ?? "")
    ? (value as LocationSpecificity)
    : "unknown"
}

/** Rank in the specificity order (unknown = 0 … exact_address = 7). */
export function specificityRank(input: LocationConfidenceInput): number {
  return LOCATION_SPECIFICITY_LEVELS.indexOf(getLocationSpecificity(input))
}

// ---------------------------------------------------------------------------
// Filter predicate shared by the map canvas, toolbar and legend
// ---------------------------------------------------------------------------

export interface LocationFilterState {
  /** 0–100, or null when the confidence filter is off. */
  confidenceThreshold: number | null
  /** Show locations at-or-above vs at-or-below the threshold. */
  confidenceDirection: "above" | "below"
  /** Specificity level, or null when the specificity filter is off. */
  specificityThreshold: LocationSpecificity | null
  /** Show locations at-least vs at-most as specific as the threshold. */
  specificityDirection: "at_least" | "at_most"
}

export function matchesLocationFilters(
  input: LocationConfidenceInput,
  filters: LocationFilterState
): boolean {
  if (filters.confidenceThreshold !== null) {
    const percent = confidencePercent(input)
    if (filters.confidenceDirection === "above") {
      if (percent < filters.confidenceThreshold) return false
    } else if (percent > filters.confidenceThreshold) {
      return false
    }
  }
  if (filters.specificityThreshold !== null) {
    const rank = specificityRank(input)
    const threshold = LOCATION_SPECIFICITY_LEVELS.indexOf(
      filters.specificityThreshold
    )
    if (filters.specificityDirection === "at_least") {
      if (rank < threshold) return false
    } else if (rank > threshold) {
      return false
    }
  }
  return true
}
