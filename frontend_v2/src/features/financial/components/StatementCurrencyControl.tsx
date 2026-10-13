import { useEffect, useRef } from "react"
import { CurrencyOptions } from "./CurrencyOptions"
import { Button } from "@/components/ui/button"

export function StatementCurrencyControl({
  currency,
  detectedCurrency,
  disabled,
  onChange,
  focus = false,
  proposal,
}: {
  currency: string
  detectedCurrency?: string
  disabled: boolean
  onChange: (currency: string) => void
  /** Opened from the queue for a currency issue: open the choice and focus it once. */
  focus?: boolean
  /** A proposed currency (value + where it comes from): one click uses it. */
  proposal?: { value: string; label: string; confirmed?: boolean }
}) {
  const useProposal = useRef<HTMLButtonElement>(null)
  const offered = !disabled && !currency && proposal?.value ? proposal : null
  const details = useRef<HTMLDetailsElement>(null)
  const select = useRef<HTMLSelectElement>(null)
  const focused = useRef(false)
  useEffect(() => {
    if (!focus || disabled || focused.current) return
    if (useProposal.current) {
      // The one-click proposal is the control the issue opens on.
      focused.current = true
      useProposal.current.focus({ preventScroll: true })
      useProposal.current.scrollIntoView?.({ block: "center", behavior: "smooth" })
      return
    }
    if (!details.current) return
    focused.current = true
    details.current.open = true
    select.current?.focus({ preventScroll: true })
    select.current?.scrollIntoView?.({ block: "center", behavior: "smooth" })
  }, [focus, disabled, offered])
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
      {offered && (
        <div
          aria-label="Proposed currency"
          className="flex flex-wrap items-center gap-2 rounded border border-teal-500/50 p-2"
        >
          <span>
            Proposed: <strong>{offered.value}</strong> ({offered.label})
          </span>
          <Button ref={useProposal} size="sm" onClick={() => onChange(offered.value)}>
            Use {offered.value}
          </Button>
        </div>
      )}
      {conflict && (
        <div
          role="alert"
          className="rounded border border-amber-500/40 bg-amber-500/5 p-3 space-y-2"
        >
          <p>
            The automatic reading suggests {detectedCurrency}; this review uses{" "}
            {currency}. Check the currency printed in this account's section before changing it.
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
      {!disabled && <details ref={details}>
        <summary className="cursor-pointer">Change currency</summary>
        <label className="block mt-2">
          Currency for this statement
          <select
            ref={select}
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
            <CurrencyOptions />
          </select>
        </label>
      </details>}
    </section>
  )
}
