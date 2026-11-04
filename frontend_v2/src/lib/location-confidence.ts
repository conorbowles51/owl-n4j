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
  geocoding_lookup_outcome?: string | null
  geocoding_lookup_mode?: string | null
}

/** Status of a pin placed by an address lookup a person asked for: a machine placement until a person confirms it. */
export const LOOKED_UP_STATUS = "looked_up"

/** A pin placed by an address lookup that no person has confirmed or moved yet. */
export function isUnconfirmedLookup(input: LocationConfidenceInput): boolean {
  return input.geocoding_status?.toLowerCase() === LOOKED_UP_STATUS && !isManuallyPlaced(input)
}

/** Flagged addresses that can be sent to the address service when a person clicks Look up. */
const LOOKUP_STATUSES = new Set(["ambiguous", "unverified", "failed", "not_run"])

/** The address a lookup sends: the one read from the evidence, else the query ingestion prepared. */
export function lookupAddress(input: { location_raw?: string | null; geocoding_query?: string | null }): string {
  return (input.location_raw || input.geocoding_query || "").trim()
}

export function canLookUp(
  input: LocationConfidenceInput & { location_raw?: string | null; geocoding_query?: string | null }
): boolean {
  if (isManuallyPlaced(input)) return false
  return LOOKUP_STATUSES.has(input.geocoding_status?.toLowerCase() ?? "") && !!lookupAddress(input)
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
 * geocodes, anything flagged ambiguous/unverified/failed/not looked up at ingestion, and pins placed by an address
 * lookup that no person has confirmed. Manually placed locations never need review.
 */
export function needsReview(input: LocationConfidenceInput): boolean {
  if (isManuallyPlaced(input)) return false
  const status = input.geocoding_status?.toLowerCase()
  if (status && (LOOKUP_STATUSES.has(status) || status === LOOKED_UP_STATUS)) {
    return true
  }
  return getConfidenceTier(input) === "low"
}

/** Human-readable reason a location is in the review queue. */
export function reviewReason(input: LocationConfidenceInput): string {
  const status = input.geocoding_status?.toLowerCase()
  if (status === LOOKED_UP_STATUS) {
    return input.geocoding_lookup_mode === "auto"
      ? "Placed by automatic address lookup · not confirmed"
      : "Placed by address lookup · not confirmed"
  }
  const outcome = input.geocoding_lookup_outcome?.toLowerCase()
  if (outcome === "no_match") return "Looked up: no match found"
  if (outcome === "unavailable") return "Looked up: the address service did not answer"
  if (status === "ambiguous") return "Ambiguous at ingestion"
  if (status === "unverified") return "Unverified at ingestion"
  if (status === "failed") return "Geocoding failed"
  // nothing was sent: an address from evidence goes to the outside address service only when a person clicks Look up
  if (status === "not_run") return "Not looked up yet"
  return "Low geocoding confidence"
}
