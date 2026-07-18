import { describe, expect, it } from "vitest"
import {
  getConfidenceTier,
  isManuallyPlaced,
  needsReview,
  reviewReason,
} from "./location-confidence"

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
  })
})
