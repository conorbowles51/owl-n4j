import type { AnalysisRun } from "./money-api"
import { levelCountWords, levelCounts } from "./strength-words"

/**
 * The thin-data line (cb-gated-spread E): the true counts by strength from the run, what the earlier build rule would
 * have hidden, and the rule-of-thumb label. Nothing is held back below a count: every candidate is listed with its
 * strength.
 */
export function StrengthLine({ run, prefix, noun, oldRule, rule }: { run: AnalysisRun; prefix: string; noun: [string, string]; oldRule: string; rule: string }) {
  const counts = levelCounts(run.counts, prefix)
  return (
    <div className="space-y-1 text-sm" data-testid="strength-line">
      <p className="font-medium">{levelCountWords(counts, noun)}</p>
      <p className="text-xs">{oldRule} Every one is listed here with its strength, however few there are.</p>
      <p className="text-xs text-muted-foreground">{rule}</p>
    </div>
  )
}
