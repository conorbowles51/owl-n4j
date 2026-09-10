import type {
  NativeControlComparison,
  CurrentNativeControls,
} from "../lib/native-control-contract"

const label = (value: string) => value.replaceAll("_", " ")
function display(value: unknown): string {
  if (value === null) return "Not available"
  if (typeof value === "boolean") return value ? "Yes" : "No"
  if (typeof value === "object") {
    if (value && "minor_units" in value && "currency" in value)
      return `${String(value.minor_units)} minor units (${String(value.currency)})`
    return JSON.stringify(value)
  }
  return String(value)
}

export function NativeControlComparisonPanel({
  comparison,
}: {
  comparison: NativeControlComparison | CurrentNativeControls
}) {
  if (!comparison.available)
    return (
      <p role="status">
        Native bank-file checks unavailable: {comparison.reason}
      </p>
    )
  const populations =
    "proposed" in comparison
      ? [
          { title: "Before correction", calculation: comparison.current },
          {
            title: "After proposed correction",
            calculation: comparison.proposed,
          },
        ]
      : [{ title: "Current source readings", calculation: comparison.current }]
  return (
    <section
      aria-label={
        "proposed" in comparison
          ? "Native bank-file control comparison"
          : "Current native bank-file controls"
      }
      className="space-y-3 rounded border p-3"
    >
      <h4 className="font-medium">Native bank-file controls</h4>
      <p>{comparison.limitation}</p>
      <p>
        {comparison.current.mapped_rows} mapped source rows;{" "}
        {comparison.current.unmapped_rows_retained} unmapped source records
        retained in the checks.
      </p>
      {populations.map(({ title, calculation }) => (
        <div key={title} className="space-y-2">
          <h5 className="font-medium">{title}</h5>
          {calculation.checks.map((check, index) => (
            <details key={index} className="rounded border p-2">
              <summary>
                {check.scope} · {label(check.kind)}:{" "}
                {label(check.result.status)}
              </summary>
              <dl className="mt-2 grid grid-cols-1 gap-1 break-words text-xs sm:grid-cols-2">
                {Object.entries(check.result)
                  .filter(([key]) => key !== "status")
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt className="font-medium">{label(key)}</dt>
                      <dd>{display(value)}</dd>
                    </div>
                  ))}
              </dl>
            </details>
          ))}
        </div>
      ))}
      <details>
        <summary>Source and calculation context</summary>
        <p className="break-all">SHA-256: {comparison.sha256}</p>
        <p>
          {comparison.parser_name} · {comparison.parser_version}
        </p>
        <p>
          {comparison.date_context.earliest}–{comparison.date_context.latest}:{" "}
          {comparison.date_context.basis}
        </p>
        <p>{comparison.current.basis}</p>
      </details>
    </section>
  )
}
