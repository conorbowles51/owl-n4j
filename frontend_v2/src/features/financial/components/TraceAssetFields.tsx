import { Button } from "@/components/ui/button"
import type { TraceAssetUse, TraceAssetResults } from "../lib/trace-assets"
import { correctionMoney } from "../lib/correction-contract"
export function TraceAssetFields({
  value,
  onChange,
  withdrawals,
}: {
  value: TraceAssetUse[]
  onChange: (value: TraceAssetUse[]) => void
  withdrawals: Array<{ id: string; label: string }>
}) {
  return (
    <fieldset className="space-y-3 rounded border p-3">
      <legend>Optional asset-use interpretations</legend>
      <p>
        Identify a whole withdrawal as funding one asset. This records your
        interpretation of its use, not ownership or current value. Partial
        purchases and resale proceeds are not inferred. A selected transfer
        cannot also fund an asset here.
      </p>
      {value.map((use, i) => (
        <div key={i} className="space-y-2 border-t pt-2">
          <label className="block">
            Source withdrawal
            <select
              aria-label={`Asset withdrawal ${i + 1}`}
              required
              className="block max-w-full border bg-background p-2"
              value={use.transaction_id}
              onChange={(e) =>
                onChange(
                  value.map((v, n) =>
                    n === i ? { ...v, transaction_id: e.target.value } : v
                  )
                )
              }
            >
              <option value="">Choose a withdrawal</option>
              {withdrawals.map((row) => (
                <option
                  key={row.id}
                  value={row.id}
                  disabled={value.some(
                    (v, n) => n !== i && v.transaction_id === row.id
                  )}
                >
                  {row.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Asset description
            <input
              aria-label={`Asset description ${i + 1}`}
              required
              maxLength={256}
              className="block w-full border bg-background p-2"
              value={use.asset_label}
              onChange={(e) =>
                onChange(
                  value.map((v, n) =>
                    n === i ? { ...v, asset_label: e.target.value } : v
                  )
                )
              }
            />
          </label>
          <label className="block">
            Basis and source interpretation
            <textarea
              aria-label={`Asset basis ${i + 1}`}
              required
              maxLength={4096}
              className="block w-full border bg-background p-2"
              value={use.basis}
              onChange={(e) =>
                onChange(
                  value.map((v, n) =>
                    n === i ? { ...v, basis: e.target.value } : v
                  )
                )
              }
            />
          </label>
          <Button
            type="button"
            variant="outline"
            onClick={() => onChange(value.filter((_, n) => n !== i))}
          >
            Remove asset interpretation {i + 1}
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        disabled={value.length >= 50 || !withdrawals.length}
        onClick={() =>
          onChange([
            ...value,
            { transaction_id: "", asset_label: "", basis: "" },
          ])
        }
      >
        Add asset interpretation
      </Button>
    </fieldset>
  )
}
export function TraceAssetResultsPanel({
  items,
  onSource,
}: {
  items: TraceAssetResults
  onSource: (id: string) => void
}) {
  if (!items.length) return null
  return (
    <section
      aria-label="Conditional asset-use allocations"
      className="space-y-2 rounded border p-3"
    >
      <h4 className="font-semibold">Conditional asset-use allocations</h4>
      {items.map((item, i) => (
        <article key={item.transaction_id} className="space-y-1">
          <p>
            {item.asset_label} · source withdrawal{" "}
            {correctionMoney(item.amount_minor, item.currency)}
          </p>
          <p>{item.basis}</p>
          {Object.entries(item.allocated_by_claim).map(([claim, amount]) => (
            <p key={claim}>
              {claim}: {correctionMoney(amount, item.currency)} allocated to
              this withdrawal under this method
            </p>
          ))}
          <p>
            Outside attributed claims:{" "}
            {correctionMoney(item.outside_claims_minor, item.currency)}; of
            which unidentified:{" "}
            {correctionMoney(item.unidentified_minor, item.currency)}; unfunded:{" "}
            {correctionMoney(item.unfunded_minor, item.currency)}.
          </p>
          <p className="text-sm">{item.limitation}</p>
          <Button
            variant="outline"
            onClick={() => onSource(item.transaction_id)}
          >
            Inspect asset payment {i + 1}
          </Button>
        </article>
      ))}
    </section>
  )
}
