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
  geocoding_status?: string | null
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
 * geocodes plus anything flagged ambiguous/unverified/failed at ingestion. Manually
 * placed locations never need review.
 */
export function needsReview(input: LocationConfidenceInput): boolean {
  if (isManuallyPlaced(input)) return false
  const status = input.geocoding_status?.toLowerCase()
  if (status === "ambiguous" || status === "unverified" || status === "failed") {
    return true
  }
  return getConfidenceTier(input) === "low"
}

/** Human-readable reason a location is in the review queue. */
export function reviewReason(input: LocationConfidenceInput): string {
  const status = input.geocoding_status?.toLowerCase()
  if (status === "ambiguous") return "Ambiguous at ingestion"
  if (status === "unverified") return "Unverified at ingestion"
  if (status === "failed") return "Geocoding failed"
  return "Low geocoding confidence"
}
