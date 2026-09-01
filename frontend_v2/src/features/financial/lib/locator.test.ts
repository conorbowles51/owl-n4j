/**
 * The reading side of the locator contract, refusal for refusal.
 *
 * `readLocator` mirrors `Locator.from_json` in the backend, and these tests
 * mirror the backend's `test_financial_locators` in intent: most of them are
 * about what is refused, because the failure this module exists to prevent is
 * a confident highlight drawn from a payload nobody actually wrote.  A parse
 * that fails loudly is working correctly.
 *
 * The happy-path payloads are shaped exactly as `Locator.to_json` emits them:
 * `{"kind": ...}` plus `page` when known, and for `page_rectangle` only,
 * `rect`, `page_size`, `units: "millipoints"`, `space: "pdf_displayed"`.
 */

import { describe, expect, it } from "vitest"

import { readLocator, normalised, type SourceRectangle } from "./locator"

/** A valid page_rectangle payload on a US-Letter page (612000x792000 mpt). */
function rectanglePayload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    kind: "page_rectangle",
    page: 3,
    rect: [153000, 198000, 306000, 396000],
    page_size: [612000, 792000],
    units: "millipoints",
    space: "pdf_displayed",
    ...overrides,
  }
}

function expectRefusal(payload: unknown, reasonPart: string | RegExp) {
  const reading = readLocator(payload)
  expect(reading.ok, `expected refusal, got ${JSON.stringify(reading)}`).toBe(false)
  if (!reading.ok) {
    expect(reading.reason).toMatch(reasonPart)
  }
}

describe("readLocator: payloads that are not locators at all", () => {
  it("refuses non-object payloads", () => {
    expectRefusal(null, /must be an object/)
    expectRefusal(undefined, /must be an object/)
    expectRefusal("page_rectangle", /must be an object/)
    expectRefusal(7, /must be an object/)
    expectRefusal([{ kind: "page_only", page: 1 }], /must be an object/)
  })

  it("refuses unknown keys rather than ignoring them", () => {
    // A key this version does not understand is a newer writer or a corrupted
    // row; dropping it silently could turn a rectangle into a page reference.
    const reading = readLocator({ kind: "page_only", page: 2, zoom: 1.5 })
    expect(reading).toEqual({
      ok: false,
      reason: 'unknown locator keys ["zoom"]; refusing to guess',
    })
  })

  it("refuses a missing, non-string, or unrecognised kind", () => {
    expectRefusal({}, /not a known locator kind/)
    expectRefusal({ kind: 4 }, /not a known locator kind/)
    expectRefusal({ kind: "paragraph" }, /not a known locator kind/)
  })
})

describe("readLocator: kind coherence, as the backend constructor enforces it", () => {
  it("refuses rectangle-only keys on kinds that are not page_rectangle", () => {
    for (const key of ["rect", "page_size", "units", "space"]) {
      expectRefusal(
        { kind: "page_only", page: 1, [key]: "anything" },
        new RegExp(`page_only carries "${key}"`),
      )
    }
  })

  it("refuses a non-integer or out-of-range page", () => {
    expectRefusal({ kind: "page_only", page: 1.5 }, /page must be an integer/)
    expectRefusal({ kind: "page_only", page: "1" }, /page must be an integer/)
    expectRefusal({ kind: "page_only", page: true }, /page must be an integer/)
    expectRefusal({ kind: "page_only", page: 0 }, /page is 1-based/)
  })

  it("page_only without a page is refused: it is a claim to know the page", () => {
    expectRefusal({ kind: "page_only" }, /none was given/)
  })

  it("page_only with a page is accepted", () => {
    expect(readLocator({ kind: "page_only", page: 4 })).toEqual({
      ok: true,
      locator: { kind: "page_only", page: 4 },
    })
  })

  it("not_positional with a page is refused: the source has no pages", () => {
    expectRefusal({ kind: "not_positional", page: 1 }, /no pages/)
  })

  it("not_positional bare is accepted", () => {
    expect(readLocator({ kind: "not_positional" })).toEqual({
      ok: true,
      locator: { kind: "not_positional" },
    })
  })

  it("unlocated permits either a known page or none", () => {
    // A reader can fail to find the value on a page it knows, or fail before
    // it knows the page. Both are honest.
    expect(readLocator({ kind: "unlocated", page: 9 })).toEqual({
      ok: true,
      locator: { kind: "unlocated", page: 9 },
    })
    expect(readLocator({ kind: "unlocated" })).toEqual({
      ok: true,
      locator: { kind: "unlocated", page: null },
    })
  })
})

describe("readLocator: page_rectangle units and space", () => {
  it("refuses units it does not know rather than rescaling", () => {
    expectRefusal(rectanglePayload({ units: "points" }), /will not rescale/)
    const missingUnits = rectanglePayload()
    delete missingUnits["units"]
    expectRefusal(missingUnits, /will not rescale/)
  })

  it("refuses a coordinate space that is not pdf_displayed", () => {
    expectRefusal(rectanglePayload({ space: "pdf_unrotated" }), /cannot be drawn without knowing/)
    const missingSpace = rectanglePayload()
    delete missingSpace["space"]
    expectRefusal(missingSpace, /cannot be drawn without knowing/)
  })
})

describe("readLocator: page_rectangle shape", () => {
  it("refuses a rect that is not four numbers", () => {
    expectRefusal(rectanglePayload({ rect: [1, 2, 3] }), /rect must be four numbers/)
    expectRefusal(rectanglePayload({ rect: "153000,198000,306000,396000" }), /rect must be four numbers/)
  })

  it("refuses a page_size that is not two numbers", () => {
    expectRefusal(rectanglePayload({ page_size: [612000] }), /page_size must be two numbers/)
    expectRefusal(rectanglePayload({ page_size: null }), /page_size must be two numbers/)
  })

  it("refuses non-integer fields, including floats and booleans", () => {
    expectRefusal(rectanglePayload({ page: 2.5 }), /page must be an integer in millipoints/)
    expectRefusal(
      rectanglePayload({ rect: [153000.5, 198000, 306000, 396000] }),
      /rect x0 must be an integer/,
    )
    expectRefusal(
      rectanglePayload({ rect: [153000, 198000, 306000, true] }),
      /rect y1 must be an integer/,
    )
    expectRefusal(
      rectanglePayload({ page_size: [612000, "792000"] }),
      /page_size height must be an integer/,
    )
  })

  it("refuses the same impossible rectangles the backend refuses", () => {
    expectRefusal(rectanglePayload({ page: 0 }), /page is 1-based/)
    expectRefusal(rectanglePayload({ page_size: [0, 792000] }), /no extent/)
    // Zero area: x1 == x0.
    expectRefusal(rectanglePayload({ rect: [153000, 198000, 153000, 396000] }), /has no area/)
    // Inverted: y1 < y0.
    expectRefusal(rectanglePayload({ rect: [153000, 396000, 306000, 198000] }), /has no area/)
    expectRefusal(rectanglePayload({ rect: [-1, 198000, 306000, 396000] }), /outside the page/)
    expectRefusal(
      rectanglePayload({ rect: [153000, 198000, 612001, 396000] }),
      /outside the 612000x792000 page/,
    )
  })

  it("accepts what the backend writes, and keeps every integer as stored", () => {
    expect(readLocator(rectanglePayload())).toEqual({
      ok: true,
      locator: {
        kind: "page_rectangle",
        page: 3,
        rectangle: {
          page: 3,
          x0: 153000,
          y0: 198000,
          x1: 306000,
          y1: 396000,
          pageWidth: 612000,
          pageHeight: 792000,
        },
      },
    })
  })

  it("accepts a rectangle that exactly fills the page", () => {
    const reading = readLocator(
      rectanglePayload({ rect: [0, 0, 612000, 792000] }),
    )
    expect(reading.ok).toBe(true)
  })
})

describe("normalised", () => {
  it("returns the rectangle as fractions of its page", () => {
    // 153000/612000 and 306000/612000 are exact quarters; 198000/792000 and
    // 396000/792000 exact quarter and half. Chosen so equality is exact.
    const rectangle: SourceRectangle = {
      page: 3,
      x0: 153000,
      y0: 198000,
      x1: 306000,
      y1: 396000,
      pageWidth: 612000,
      pageHeight: 792000,
    }
    expect(normalised(rectangle)).toEqual({ x0: 0.25, y0: 0.25, x1: 0.5, y1: 0.5 })
  })

  it("uses width for x and height for y, not one for both", () => {
    const rectangle: SourceRectangle = {
      page: 1,
      x0: 0,
      y0: 0,
      x1: 612000,
      y1: 198000,
      pageWidth: 612000,
      pageHeight: 792000,
    }
    expect(normalised(rectangle)).toEqual({ x0: 0, y0: 0, x1: 1, y1: 0.25 })
  })
})
