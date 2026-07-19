import { describe, expect, it } from "vitest"
import {
  confidencePercent,
  getConfidenceTier,
  getLocationSpecificity,
  isManuallyPlaced,
  matchesLocationFilters,
  needsReview,
  reviewReason,
  specificityRank,
  type LocationFilterState,
} from "./location-confidence"

const NO_FILTERS: LocationFilterState = {
  confidenceThreshold: null,
  confidenceDirection: "above",
  specificityThreshold: null,
  specificityDirection: "at_least",
}

describe("getConfidenceTier", () => {
  it("maps geocoder confidence values to tiers", () => {
    expect(getConfidenceTier({ geocoding_confidence: "high" })).toBe("high")
    expect(getConfidenceTier({ geocoding_confidence: "medium" })).toBe("medium")
    expect(getConfidenceTier({ geocoding_confidence: "low" })).toBe("low")
    expect(getConfidenceTier({ geocoding_confidence: "HIGH" })).toBe("high")
  })

  it("falls back to unverified for missing or unknown values", () => {
    expect(getConfidenceTier({})).toBe("unverified")
    expect(getConfidenceTier({ geocoding_confidence: "exact" })).toBe("unverified")
  })

  it("manual placement always outranks automatic tiers", () => {
    expect(
      getConfidenceTier({
        geocoding_confidence: "low",
        manual_fields: ["latitude", "longitude"],
      })
    ).toBe("manual")
    expect(
      getConfidenceTier({
        geocoding_confidence: "high",
        manual_fields: ["longitude"],
      })
    ).toBe("manual")
  })
})

describe("isManuallyPlaced", () => {
  it("only counts location-related manual fields", () => {
    expect(isManuallyPlaced({ manual_fields: ["summary", "name"] })).toBe(false)
    expect(isManuallyPlaced({ manual_fields: ["latitude"] })).toBe(true)
    expect(isManuallyPlaced({ manual_fields: undefined })).toBe(false)
  })
})

describe("needsReview", () => {
  it("flags low-confidence geocodes", () => {
    expect(needsReview({ geocoding_confidence: "low" })).toBe(true)
    expect(needsReview({ geocoding_confidence: "high" })).toBe(false)
    expect(needsReview({ geocoding_confidence: "medium" })).toBe(false)
  })

  it("flags ambiguous, unverified and failed ingestion statuses regardless of confidence", () => {
    expect(needsReview({ geocoding_status: "ambiguous" })).toBe(true)
    expect(needsReview({ geocoding_status: "unverified" })).toBe(true)
    expect(needsReview({ geocoding_status: "failed" })).toBe(true)
    expect(
      needsReview({ geocoding_status: "success", geocoding_confidence: "high" })
    ).toBe(false)
  })

  it("flags locations explicitly classified as unknown specificity", () => {
    expect(
      needsReview({
        geocoding_confidence: "high",
        location_specificity: "unknown",
      })
    ).toBe(true)
    expect(
      needsReview({
        geocoding_confidence: "high",
        location_specificity: "city",
      })
    ).toBe(false)
  })

  it("never lists manually placed locations", () => {
    expect(
      needsReview({
        geocoding_confidence: "low",
        manual_fields: ["latitude", "longitude"],
      })
    ).toBe(false)
    expect(
      needsReview({
        geocoding_status: "ambiguous",
        manual_fields: ["latitude"],
      })
    ).toBe(false)
  })
})

describe("reviewReason", () => {
  it("describes why a location is queued", () => {
    expect(reviewReason({ geocoding_status: "ambiguous" })).toBe(
      "Ambiguous at ingestion"
    )
    expect(reviewReason({ geocoding_status: "unverified" })).toBe(
      "Unverified at ingestion"
    )
    expect(reviewReason({ geocoding_status: "failed" })).toBe("Geocoding failed")
    expect(reviewReason({ geocoding_confidence: "low" })).toBe(
      "Low geocoding confidence"
    )
    expect(
      reviewReason({
        geocoding_confidence: "high",
        location_specificity: "unknown",
      })
    ).toBe("Unknown address specificity")
  })
})

describe("confidencePercent", () => {
  it("uses the geocoder's raw score when present", () => {
    expect(
      confidencePercent({
        geocoding_confidence: "high",
        geocoding_confidence_score: 0.83,
      })
    ).toBe(83)
    expect(
      confidencePercent({
        geocoding_confidence: "low",
        geocoding_confidence_score: 0.12,
      })
    ).toBe(12)
  })

  it("clamps out-of-range scores to 0-100", () => {
    expect(
      confidencePercent({ geocoding_confidence_score: 1.4 })
    ).toBe(100)
    expect(
      confidencePercent({ geocoding_confidence_score: -0.2 })
    ).toBe(0)
  })

  it("falls back to representative percentages without a score", () => {
    expect(confidencePercent({ geocoding_confidence: "high" })).toBe(85)
    expect(confidencePercent({ geocoding_confidence: "medium" })).toBe(55)
    expect(confidencePercent({ geocoding_confidence: "low" })).toBe(20)
    expect(confidencePercent({})).toBe(0)
  })

  it("always reports manual placements as 100%", () => {
    expect(
      confidencePercent({
        geocoding_confidence: "low",
        geocoding_confidence_score: 0.1,
        manual_fields: ["latitude"],
      })
    ).toBe(100)
  })
})

describe("location specificity", () => {
  it("normalizes values and orders them unknown -> exact_address", () => {
    expect(getLocationSpecificity({ location_specificity: "CITY" })).toBe("city")
    expect(getLocationSpecificity({ location_specificity: "nonsense" })).toBe(
      "unknown"
    )
    expect(getLocationSpecificity({})).toBe("unknown")
    expect(specificityRank({ location_specificity: "unknown" })).toBe(0)
    expect(
      specificityRank({ location_specificity: "country" })
    ).toBeLessThan(specificityRank({ location_specificity: "city" }))
    expect(specificityRank({ location_specificity: "exact_address" })).toBe(7)
  })
})

describe("matchesLocationFilters", () => {
  it("passes everything when both filters are off", () => {
    expect(
      matchesLocationFilters({ geocoding_confidence: "low" }, NO_FILTERS)
    ).toBe(true)
  })

  it("filters above a confidence threshold", () => {
    const filters = { ...NO_FILTERS, confidenceThreshold: 60 }
    expect(
      matchesLocationFilters({ geocoding_confidence_score: 0.9 }, filters)
    ).toBe(true)
    expect(
      matchesLocationFilters({ geocoding_confidence_score: 0.3 }, filters)
    ).toBe(false)
  })

  it("filters below a confidence threshold for finding things to update", () => {
    const filters: LocationFilterState = {
      ...NO_FILTERS,
      confidenceThreshold: 60,
      confidenceDirection: "below",
    }
    expect(
      matchesLocationFilters({ geocoding_confidence_score: 0.3 }, filters)
    ).toBe(true)
    expect(
      matchesLocationFilters({ geocoding_confidence_score: 0.9 }, filters)
    ).toBe(false)
    // Manual locations sit at 100% and are excluded by a "below" filter
    expect(
      matchesLocationFilters({ manual_fields: ["latitude"] }, filters)
    ).toBe(false)
  })

  it("filters by address specificity in both directions", () => {
    const atLeastCity: LocationFilterState = {
      ...NO_FILTERS,
      specificityThreshold: "city",
      specificityDirection: "at_least",
    }
    expect(
      matchesLocationFilters({ location_specificity: "street" }, atLeastCity)
    ).toBe(true)
    expect(
      matchesLocationFilters({ location_specificity: "country" }, atLeastCity)
    ).toBe(false)

    const atMostCity: LocationFilterState = {
      ...atLeastCity,
      specificityDirection: "at_most",
    }
    expect(
      matchesLocationFilters({ location_specificity: "country" }, atMostCity)
    ).toBe(true)
    expect(
      matchesLocationFilters({ location_specificity: "street" }, atMostCity)
    ).toBe(false)
  })

  it("applies both axes together", () => {
    const filters: LocationFilterState = {
      confidenceThreshold: 50,
      confidenceDirection: "above",
      specificityThreshold: "city",
      specificityDirection: "at_least",
    }
    expect(
      matchesLocationFilters(
        { geocoding_confidence_score: 0.8, location_specificity: "street" },
        filters
      )
    ).toBe(true)
    expect(
      matchesLocationFilters(
        { geocoding_confidence_score: 0.8, location_specificity: "country" },
        filters
      )
    ).toBe(false)
  })
})
