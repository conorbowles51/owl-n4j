import { useState } from "react"
import { artifactRows, artifactText } from "../artifact-data"
import { evaluateScenario } from "../scenario-expression"

export function ArtifactScenario({ interactions }: { interactions: Record<string, unknown> }) {
  const inputs = artifactRows(interactions.inputs)
  const [entered, setEntered] = useState<Record<string, string>>({})
  const values = new Map<string, number>()
  for (const input of inputs) {
    const key = artifactText(input.key)
    const raw = entered[key] ?? artifactText(input.value)
    const value = Number(raw)
    if (raw.trim() && Number.isFinite(value)) values.set(key, value)
  }
  const results = artifactRows(interactions.calculations).map((calculation) => {
    try {
      const value = evaluateScenario(artifactText(calculation.expression), values)
      values.set(artifactText(calculation.key), value)
      return { calculation, value, error: "" }
    } catch (e) { return { calculation, value: null, error: e instanceof Error ? e.message : "Check this calculation." } }
  })
  return <section aria-label="Scenario calculator" className="rounded-lg border border-border bg-muted/20 p-4">
    <h3 className="text-sm font-semibold">Explore assumptions</h3>
    <p className="mt-1 text-xs text-muted-foreground">Scenario values only. Editing these inputs does not change evidence or saved case records.</p>
    <div className="my-4 grid grid-cols-1 gap-3 sm:grid-cols-2">{inputs.map((input) => {
      const key = artifactText(input.key)
      return <label key={key} className="block text-xs font-medium">{artifactText(input.label || key)}<input type="number" step={typeof input.step === "number" ? input.step : "any"} min={typeof input.min === "number" ? input.min : undefined} max={typeof input.max === "number" ? input.max : undefined} value={entered[key] ?? artifactText(input.value)} onChange={(e) => setEntered((current) => ({ ...current, [key]: e.target.value }))} className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm" /></label>
    })}</div>
    <dl aria-live="polite" className="space-y-3">{results.map(({ calculation, value, error }) => <div key={artifactText(calculation.key)} className="border-t border-border pt-3">
      <dt className="text-xs text-muted-foreground">{artifactText(calculation.label || calculation.key)}</dt>
      <dd className={error ? "mt-1 text-xs text-destructive" : "mt-1 text-xl font-semibold tabular-nums"}>{error || value?.toLocaleString(undefined, { maximumFractionDigits: typeof calculation.decimals === "number" && Number.isFinite(calculation.decimals) ? Math.min(10, Math.max(0, Math.floor(calculation.decimals))) : 2 })}</dd>
      <p className="mt-1 text-xs text-muted-foreground">Calculation: {artifactText(calculation.expression)}</p>
    </div>)}</dl>
  </section>
}
