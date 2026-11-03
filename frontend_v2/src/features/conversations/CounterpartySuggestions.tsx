import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { getCounterpartySuggestions } from "@/features/phones/api"

const fmt = (n: number) => n.toLocaleString("en-US")

function money(minor: number, currency: string) {
  // the currency's own minor unit (JPY has none, USD two), never a fixed hundredth
  try {
    const f = new Intl.NumberFormat("en-US", { style: "currency", currency })
    return f.format(minor / 10 ** (f.resolvedOptions().maximumFractionDigits ?? 2))
  } catch {
    return `${currency} ${minor} (minor units)`
  }
}

/**
 * XF-8 (07 section 7.2): a phone contact's number or address that is the reference of a reviewed account (a payment
 * service addressed by phone number or email) suggests that account's payments. Always "Suggested, not reviewed":
 * nothing on the ledger changes here. In a case with no financial evidence it says so and never shows 0 payments.
 */
export function CounterpartySuggestions({ caseId, identityKey }: { caseId: string; identityKey: string }) {
  const [open, setOpen] = useState(false)
  const contact = identityKey.startsWith("phone:") || identityKey.startsWith("email:")
  const q = useQuery({
    queryKey: ["counterparty-suggestions", caseId, identityKey],
    queryFn: () => getCounterpartySuggestions(caseId, identityKey),
    enabled: !!caseId && contact,
    staleTime: 60_000,
    retry: false,
  })
  if (!contact || !q.data || q.data.state === "none") return null
  const d = q.data
  return (
    <section aria-label="Payments suggested for this contact" className="rounded border p-2 text-xs">
      <p>{d.sentence}</p>
      {d.state === "suggested" && (
        <>
          <button type="button" className="underline" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide these payments" : "Open these payments"}
          </button>
          {open && (
            <ul className="mt-1 flex flex-col gap-0.5">
              {(d.payments ?? []).map((p) => (
                <li key={p.id}>
                  <Link className="underline" to={p.href}>
                    {p.date ?? "No date"}: {money(p.amount_minor, p.currency)} {p.direction === "credit" ? "in" : "out"}
                    {p.description ? `, ${p.description}` : ""}
                  </Link>
                </li>
              ))}
              {d.limitation && <li className="text-muted-foreground">{d.limitation}</li>}
              <li className="text-muted-foreground">
                {fmt(d.payment_total ?? 0)} in all. The account is matched by its reference, not reviewed as this
                person's. Confirm it in Financial before relying on it.
              </li>
            </ul>
          )}
        </>
      )}
    </section>
  )
}
