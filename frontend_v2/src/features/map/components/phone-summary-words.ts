import type { PhoneMapSummary } from "@/features/phones/api"

const n = (v: number) => v.toLocaleString("en-US")

/** The words above the phone layer (03 13.3): "Showing 1,204 of 1,260 positioned records. 56 cannot be placed (why)." */
export function phoneSummaryWords(summary: PhoneMapSummary, shown: number) {
  const unplaced = summary.not_positionable.reduce((a, m) => a + m.count, 0)
  return {
    showing: `Showing ${n(shown)} of ${n(summary.total)} positioned records.`,
    unplaced: unplaced ? `${n(unplaced)} cannot be placed` : null,
  }
}
