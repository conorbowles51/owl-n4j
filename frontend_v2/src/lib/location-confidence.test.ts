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

describe("addresses looked up only when a person asks", () => {
  it("lists addresses not looked up yet with a Look up action", async () => {
    const { needsReview: nr, reviewReason: rr, canLookUp } = await import("./location-confidence")
    expect(nr({ geocoding_status: "not_run" })).toBe(true)
    expect(rr({ geocoding_status: "not_run" })).toBe("Not looked up yet")
    expect(canLookUp({ geocoding_status: "failed", location_raw: "12 Main St" })).toBe(true)
    expect(canLookUp({ geocoding_status: "failed", location_raw: " " })).toBe(false)
    expect(canLookUp({ geocoding_status: "success", location_raw: "12 Main St" })).toBe(false)
    expect(canLookUp({ geocoding_status: "failed", location_raw: "12 Main St", manual_fields: ["latitude"] })).toBe(
      false
    )
  })

  it("keeps a looked-up pin under review as a machine placement until a person confirms it", async () => {
    const { needsReview: nr, reviewReason: rr, isUnconfirmedLookup, getConfidenceTier: tier } = await import(
      "./location-confidence"
    )
    const lookedUp = { geocoding_status: "looked_up", geocoding_confidence: "high" }
    expect(nr(lookedUp)).toBe(true)
    expect(isUnconfirmedLookup(lookedUp)).toBe(true)
    expect(rr(lookedUp)).toBe("Placed by address lookup · not confirmed")
    const confirmed = { ...lookedUp, manual_fields: ["latitude", "longitude"] }
    expect(nr(confirmed)).toBe(false)
    expect(isUnconfirmedLookup(confirmed)).toBe(false)
    expect(tier(confirmed)).toBe("manual")
  })

  it("says what a lookup found when it found nothing", async () => {
    const { reviewReason: rr } = await import("./location-confidence")
    expect(rr({ geocoding_status: "failed", geocoding_lookup_outcome: "no_match" })).toBe("Looked up: no match found")
    expect(rr({ geocoding_status: "failed", geocoding_lookup_outcome: "unavailable" })).toBe(
      "Looked up: the address service did not answer"
    )
  })

  it("says why the automatic lookup left an address for a person, and keeps a removed pin in view", async () => {
    // lx-demo 10 Nov 2026: "gate house" was pinned in Norwich by the automatic lookup
    const { reviewReason: rr } = await import("./location-confidence")
    expect(rr({ geocoding_status: "failed", geocoding_lookup_outcome: "not_a_place" })).toBe(
      "Not looked up automatically: the text names no place on its own"
    )
    expect(
      rr({
        geocoding_status: "failed",
        geocoding_lookup_outcome: "outside_case_region",
        geocoding_withdrawn_formatted_address: "Kent County, Texas, United States",
      })
    ).toBe(
      "Looked up: the only match was outside the state the case names · earlier automatic pin removed: Kent County, Texas, United States"
    )
  })
})
