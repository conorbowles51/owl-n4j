import { Button } from "@/components/ui/button"

export function StatementCurrencyControl({
  currency,
  detectedCurrency,
  disabled,
  onChange,
}: {
  currency: string
  detectedCurrency?: string
  disabled: boolean
  onChange: (currency: string) => void
}) {
  const conflict = !!detectedCurrency && currency !== detectedCurrency
  return (
    <section aria-label="Statement currency" className="space-y-2 text-sm">
      <p>
        Statement currency: <strong>{currency || "Not identified"}</strong>
        {detectedCurrency === currency && currency && (
          <span className="ml-2 text-muted-foreground">
            Detected from statement
          </span>
        )}
      </p>
      {conflict && (
        <div
          role="alert"
          className="rounded border border-amber-500/40 bg-amber-500/5 p-3 space-y-2"
        >
          <p>
            This statement uses {detectedCurrency}, but the review was set to{" "}
            {currency}. This can leave amounts blank and flag otherwise readable
            transactions.
          </p>
          <Button
            variant="outline"
            disabled={disabled}
            onClick={() => onChange("")}
          >
            Use {detectedCurrency} from statement
          </Button>
        </div>
      )}
      <details>
        <summary className="cursor-pointer">Change currency</summary>
        <label className="block mt-2">
          Currency for this statement
          <select
            aria-label="Currency for this statement"
            className="ml-2 rounded border bg-background p-2"
            disabled={disabled}
            value={currency}
            onChange={(event) => onChange(event.target.value)}
          >
            <option value="">
              {detectedCurrency
                ? `Automatic (${detectedCurrency})`
                : "Choose currency"}
            </option>
            {Array.from(
              new Set([
                currency,
                detectedCurrency,
                "USD",
                "EUR",
                "GBP",
                "CAD",
                "AUD",
                "JPY",
                "KWD",
                ...(typeof Intl.supportedValuesOf === "function"
                  ? Intl.supportedValuesOf("currency")
                  : []),
              ])
            )
              .filter((code): code is string => !!code)
              .map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
          </select>
        </label>
      </details>
    </section>
  )
}
