import type { AIInsight, VerifiedFact } from "@/types/graph.types"

export interface AiItemsSummary {
  facts: number
  pinnedFacts: number
  insights: number
  personVerified: number
  notReviewed: number
  rejected: number
}

/** One line of counts for an entity's AI-made facts and insights, so the panel leads with the whole picture. */
export function summariseAiItems(facts: VerifiedFact[], insights: AIInsight[]): AiItemsSummary {
  return {
    facts: facts.length,
    pinnedFacts: facts.filter((f) => f.pinned).length,
    insights: insights.length,
    personVerified: insights.filter((i) => i.verified && !i.rejected).length,
    notReviewed: insights.filter((i) => !i.verified && !i.rejected).length,
    rejected: insights.filter((i) => i.rejected).length,
  }
}

export function aiItemsLine(s: AiItemsSummary): string {
  const parts = [`${s.facts} source-grounded fact${s.facts === 1 ? "" : "s"}${s.pinnedFacts ? ` (${s.pinnedFacts} pinned)` : ""}`]
  parts.push(
    s.insights
      ? `${s.insights} insight${s.insights === 1 ? "" : "s"}: ${s.personVerified} confirmed by a person, ${s.notReviewed} not reviewed, ${s.rejected} rejected`
      : "no insights",
  )
  return `AI-made · ${parts.join(" · ")}`
}

/**
 * Insights in review order with their original positions kept (verify/reject act on the stored index): not reviewed
 * first, then confirmed; rejected ones are listed apart and shown only on request. Nothing is dropped.
 */
export function orderInsights(insights: AIInsight[]) {
  const indexed = insights.map((insight, index) => ({ insight, index }))
  return {
    open: indexed.filter(({ insight }) => !insight.verified && !insight.rejected),
    confirmed: indexed.filter(({ insight }) => insight.verified && !insight.rejected),
    rejected: indexed.filter(({ insight }) => insight.rejected),
  }
}
