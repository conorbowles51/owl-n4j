import { describe, expect, it } from "vitest"
import {
  chartMonths,
  chartTotal,
  conflicts,
  entityColours,
  evidenceFiles,
  graphCounts,
  invoiceDescriptions,
  passThrough,
  recitedAmounts,
  sourcedEntities,
  transcript,
} from "./case"

describe("convergence", () => {
  it("the amounts Blackwood recites match the ledger, in order", () => {
    const spoken = transcript.find((t) => t.at === "00:35")
    expect(spoken?.text).toContain("vary the amounts")

    const ledger = chartMonths
      .filter((m) => m.amount > 0)
      .map((m) => m.amount)
      .slice(0, recitedAmounts.length)

    expect(ledger).toEqual(recitedAmounts)
  })

  it("the disputed December figure is the one argued about on the call", () => {
    expect(chartMonths.find((m) => m.month === "Dec")?.amount).toBe(275_000)
    expect(transcript.some((t) => t.text.includes("Two seventy five"))).toBe(true)
  })

  it("the December invoice description is the phrase spoken on the call", () => {
    const december = invoiceDescriptions.at(-1)
    expect(december?.description).toBe("Year-End Advisory Services")
    expect(december?.amount).toBe(275_000)

    // "Year end advisory." spoken 19 Dec vs "Year-End Advisory Services" filed 20 Dec.
    // Compare on letters alone so hyphenation and the trailing noun do not matter.
    const letters = (s: string) => s.toLowerCase().replace(/[^a-z]/g, "")
    const spoken = transcript.find((t) => t.text === "Year end advisory.")
    expect(spoken).toBeDefined()
    expect(letters(december!.description)).toContain(letters(spoken!.text))
  })

  it("the invoice schedule totals the charted year", () => {
    const sum = invoiceDescriptions.reduce((n, i) => n + i.amount, 0)
    expect(sum).toBe(chartTotal)
    expect(chartMonths.reduce((n, m) => n + m.amount, 0)).toBe(chartTotal)
  })

  it("the onward leg is a smaller number than the inbound leg", () => {
    expect(passThrough.inbound).toBe(chartTotal)
    expect(passThrough.onward).toBeLessThan(passThrough.inbound)
    const ratio = passThrough.onward / passThrough.inbound
    expect(Number((ratio * 100).toFixed(1))).toBe(96.6)
  })
})

describe("graph counts", () => {
  it("entity type counts sum to the node total", () => {
    const sum = graphCounts.all.types.reduce((n, t) => n + t.count, 0)
    expect(sum).toBe(graphCounts.all.nodes)
  })

  it("the significant layer sums to its own node total", () => {
    const sum = graphCounts.significant.types.reduce((n, t) => n + t.count, 0)
    expect(sum).toBe(graphCounts.significant.nodes)
  })

  it("the significant layer is a strict reduction", () => {
    expect(graphCounts.significant.nodes).toBeLessThan(graphCounts.all.nodes)
    expect(graphCounts.significant.types.length).toBeLessThan(graphCounts.all.types.length)
  })
})

describe("citations", () => {
  const names = new Set(evidenceFiles.map((f) => f.name))

  it("every conflict cites a file that exists in the case", () => {
    for (const conflict of conflicts) {
      expect(names.has(conflict.chen.file)).toBe(true)
      expect(names.has(conflict.okonkwo.file)).toBe(true)
    }
  })

  it("every sourced entity cites a file that exists in the case", () => {
    for (const entity of sourcedEntities) {
      expect(names.has(entity.file)).toBe(true)
    }
  })

  it("every sourced entity has a colour in the palette", () => {
    for (const entity of sourcedEntities) {
      expect(entityColours[entity.type]).toBeDefined()
    }
  })

  it("every entity type in the graph legend has a colour", () => {
    for (const { type } of graphCounts.all.types) {
      expect(entityColours[type]).toBeDefined()
    }
  })
})
