import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { createPayeeDossier, getPaymentCrossing, type PaymentCrossing } from "@/features/phones/api"

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const fmt = (n: number) => n.toLocaleString("en-US")
const items = (n: number) => `${fmt(n)} ${n === 1 ? "message or call" : "messages and calls"}`

/**
 * XF-1 (07 section 7.2): phone activity around a payment. The payment's reviewed counterparty, through the person
 * linked to it, to that person's messages and calls on the phones the day before, the same day and the day after.
 * A payment has a date and no time, so the words are days, never a time of day. Each count is the Conversations
 * count for the link beside it. Nothing here changes the payment.
 */
export function PaymentPhoneActivity({ caseId, transactionId }: { caseId?: string; transactionId: string }) {
  const ok = !!caseId && UUID.test(transactionId)
  // fetched directly: the payment panel is also shown where no query client is mounted
  const [data, setData] = useState<PaymentCrossing | null>(null)
  const [failed, setFailed] = useState(false)
  const [made, setMade] = useState<{ id: string; name: string } | null>(null)
  const [making, setMaking] = useState(false)
  const [makeError, setMakeError] = useState<string | null>(null)
  useEffect(() => {
    setData(null)
    setFailed(false)
    setMade(null)
    if (!ok) return
    let live = true
    getPaymentCrossing(caseId!, transactionId)
      .then((d) => { if (live) setData(d) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [ok, caseId, transactionId])
  if (!ok || (data && data.state === "no_phones")) return null
  const makeDossier = async () => {
    setMaking(true)
    setMakeError(null)
    try {
      const d = await createPayeeDossier(caseId!, transactionId)
      setMade({ id: d.id, name: d.display_name })
    } catch (e) {
      setMakeError(e instanceof Error ? e.message : "The dossier could not be made.")
    } finally {
      setMaking(false)
    }
  }
  const person = data?.people?.[0]
  return (
    <section aria-label="Phone activity around this payment" data-testid="payment-phone-activity" className="text-sm">
      <h4 className="font-medium">Phone activity around this payment</h4>
      {failed && <p className="text-muted-foreground">The phones could not be read just now. The payment is unaffected.</p>}
      {!data && !failed && <p className="text-muted-foreground">Reading the phones…</p>}
      {data && data.state === "linked" && (
        <>
          <p>{data.sentence}</p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {data.days.map((d) => (
              <li key={d.offset}>
                <Link className="underline" to={d.conversations_href}>
                  {d.words}: {items(d.count)}
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-1 flex flex-wrap gap-3">
            {data.conversations_href && (
              <Link className="underline" to={data.conversations_href}>Open all {fmt(data.total ?? 0)} in Conversations</Link>
            )}
            {person && data.payment_date && (
              <Link className="underline"
                to={`/cases/${encodeURIComponent(caseId!)}/phone-patterns?view=day&subject=${encodeURIComponent(`d:${person.id}`)}&day=${data.payment_date}`}>
                Lanes for {person.name} on the payment day
              </Link>
            )}
          </p>
        </>
      )}
      {data && data.state !== "linked" && <p>{data.sentence}</p>}
      {data && data.state === "unlinked" && (
        <p className="mt-1 flex flex-wrap items-center gap-3">
          <Link className="underline" to={`/cases/${encodeURIComponent(caseId!)}/dossiers`}>Open People</Link>
          {data.payee_dossier_offer && !made && (
            <button type="button" className="underline" disabled={making} onClick={makeDossier}>
              {making ? "Making a dossier…" : `Make a dossier for ${data.counterparty?.label || "this payee"}`}
            </button>
          )}
          {made && (
            <span role="status">
              Dossier made for {made.name}. <Link className="underline" to={`/cases/${encodeURIComponent(caseId!)}/dossiers?dossier=${encodeURIComponent(made.id)}`}>Open it</Link> to link the payee and their phones.
            </span>
          )}
        </p>
      )}
      {makeError && <p role="alert">{makeError}</p>}
    </section>
  )
}
