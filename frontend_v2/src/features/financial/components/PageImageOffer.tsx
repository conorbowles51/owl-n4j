import { useState } from "react"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"

/** The values compared: header, balances, payments and their totals (minor units as text). */
export interface OfferValues {
  holder?: string
  account_number?: string
  institution?: string
  currency?: string
  period_start?: string
  period_end?: string
  opening_minor?: string | null
  closing_minor?: string | null
  payments?: number
  credits_minor?: string
  debits_minor?: string
}

export interface PageImageOfferData {
  /** Which offer this is: a choice is refused if the offer changed since it was shown. */
  id: string
  mine: OfferValues
  offered: OfferValues
}

function money(minor: string | null | undefined, currency: string) {
  if (minor === null || minor === undefined || minor === "") return "not entered"
  const negative = minor.startsWith("-")
  const digits = (negative ? minor.slice(1) : minor).padStart(3, "0")
  const whole = Number(digits.slice(0, -2)).toLocaleString("en-US")
  return `${negative ? "-" : ""}${whole}.${digits.slice(-2)}${currency ? ` ${currency}` : ""}`
}

const ROWS: { label: string; value: (v: OfferValues) => string }[] = [
  { label: "Holder", value: (v) => v.holder || "not entered" },
  { label: "Account", value: (v) => v.account_number || "not entered" },
  { label: "Bank", value: (v) => v.institution || "not entered" },
  { label: "Currency", value: (v) => v.currency || "not entered" },
  { label: "Period", value: (v) => (v.period_start || v.period_end ? `${v.period_start || "?"} to ${v.period_end || "?"}` : "not entered") },
  { label: "Opening balance", value: (v) => money(v.opening_minor, v.currency ?? "") },
  { label: "Closing balance", value: (v) => money(v.closing_minor, v.currency ?? "") },
  { label: "Payments", value: (v) => String(v.payments ?? 0) },
  { label: "Money in", value: (v) => money(v.credits_minor, v.currency ?? "") },
  { label: "Money out", value: (v) => money(v.debits_minor, v.currency ?? "") },
]

/**
 * A reading of this statement's page images that checks out, offered beside the
 * person's own saved work (rule 2). Nothing of theirs changes unless they choose
 * "Use this reading", which saves it as their own review (their earlier review
 * stays in its history); "Keep mine" sets the offer aside.
 */
export function PageImageOffer({
  caseId,
  batchId,
  itemId,
  offer,
  canEdit,
  onDone,
}: {
  caseId: string
  batchId: string
  itemId: string
  offer: PageImageOfferData
  canEdit: boolean
  onDone: (used: boolean) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const answer = async (choice: "accept" | "decline") => {
    setBusy(true)
    setError("")
    try {
      await fetchAPI(
        `/api/financial/statement-import/batches/${batchId}/items/${itemId}/page-image-offer/${choice}?case_id=${caseId}&offer_id=${encodeURIComponent(offer.id)}`,
        { method: "POST" }
      )
      onDone(choice === "accept")
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The choice could not be saved.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <section aria-label="Reading from the page images" className="mt-2 space-y-2 rounded border border-teal-500/60 p-2 text-xs">
      <p className="font-medium">A reading from the page images checks out</p>
      <p className="text-muted-foreground">
        Every payment, the balances and the printed totals agree to the cent. Your saved work stays as it is unless you
        choose to use this reading.
      </p>
      <table className="w-full tabular-nums">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="font-normal" />
            <th className="font-normal">Your saved work</th>
            <th className="font-normal">From the page images</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => {
            const mine = row.value(offer.mine)
            const offered = row.value(offer.offered)
            return (
              <tr key={row.label} className={mine !== offered ? "font-medium" : ""}>
                <td className="pr-2 text-muted-foreground">{row.label}</td>
                <td>{mine}</td>
                <td>{offered}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {canEdit && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => void answer("accept")}>
            Use this reading
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void answer("decline")}>
            Keep mine
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
    </section>
  )
}
