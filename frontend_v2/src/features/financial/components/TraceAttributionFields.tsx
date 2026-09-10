import { Button } from "@/components/ui/button"
export type DraftAttribution = {
  transaction_id: string
  claim_id: string
  amount_input: string
  basis: string
}
export function TraceAttributionFields({
  currency,
  credits,
  value,
  onChange,
}: {
  currency: string
  credits: { id: string; label: string }[]
  value: DraftAttribution[]
  onChange: (value: DraftAttribution[]) => void
}) {
  const change = (index: number, field: keyof DraftAttribution, text: string) =>
    onChange(value.map((a, i) => (i === index ? { ...a, [field]: text } : a)))
  return (
    <>
      <p>
        Attribute one or more deposits to claims. A deposit can be split between
        claims up to its recorded amount. Opening funds remain unattributed.
      </p>
      {value.map((a, i) => (
        <fieldset className="space-y-2 rounded border p-3" key={i}>
          <legend>Deposit attribution {i + 1}</legend>
          {a.transaction_id &&
            !credits.some((c) => c.id === a.transaction_id) && (
              <p role="alert">
                This deposit is no longer eligible in this scenario. Choose
                another credit or remove the attribution.
              </p>
            )}
          <label className="block">
            Attributed deposit
            <select
              aria-label={
                i === 0 ? "Attributed deposit" : `Attributed deposit ${i + 1}`
              }
              className="border bg-background p-1"
              required
              value={a.transaction_id}
              onChange={(e) => change(i, "transaction_id", e.target.value)}
            >
              <option value="">Choose a credit reading</option>
              {credits.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Claim label
            <input
              aria-label={i === 0 ? "Claim label" : `Claim label ${i + 1}`}
              className="border bg-background p-1"
              required
              maxLength={128}
              value={a.claim_id}
              onChange={(e) => change(i, "claim_id", e.target.value)}
            />
          </label>
          <label className="block">
            Attributed amount ({currency})
            <input
              aria-label={
                i === 0
                  ? `Attributed amount (${currency})`
                  : `Attributed amount ${i + 1} (${currency})`
              }
              className="border bg-background p-1"
              required
              inputMode="decimal"
              maxLength={32}
              value={a.amount_input}
              onChange={(e) => change(i, "amount_input", e.target.value)}
            />
          </label>
          <label className="block">
            Attribution basis
            <textarea
              aria-label={
                i === 0 ? "Attribution basis" : `Attribution basis ${i + 1}`
              }
              className="block w-full border bg-background p-1"
              required
              maxLength={4096}
              value={a.basis}
              onChange={(e) => change(i, "basis", e.target.value)}
            />
          </label>
          {value.length > 1 && (
            <Button
              type="button"
              variant="outline"
              onClick={() => onChange(value.filter((_, index) => index !== i))}
            >
              Remove attribution {i + 1}
            </Button>
          )}
        </fieldset>
      ))}
      <Button
        type="button"
        variant="outline"
        disabled={value.length >= 50}
        onClick={() =>
          onChange([
            ...value,
            { transaction_id: "", claim_id: "", amount_input: "", basis: "" },
          ])
        }
      >
        Add deposit attribution
      </Button>
    </>
  )
}
