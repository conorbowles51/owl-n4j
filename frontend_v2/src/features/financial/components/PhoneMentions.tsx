import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { instantWords } from "@/features/phones/lib/time-words"
import { moneyAPI, type PhoneLink } from "@/features/phones/analysis/money-api"

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** "Also recorded on phone C1: notification at …" (05 section 4.4). A link to the phone record only: the payment's
 * class and values are unchanged, and the phone reading stays a reading from the phone. */
export function PhoneMentions({ caseId, transactionId }: { caseId?: string; transactionId: string }) {
  const ok = !!caseId && UUID.test(transactionId)
  // fetched directly: the payment panel is also shown where no query client is mounted
  const [links, setLinks] = useState<PhoneLink[]>([])
  useEffect(() => {
    setLinks([])
    if (!ok) return
    let live = true
    moneyAPI.ledgerLinks(caseId!, [transactionId]).then((d) => { if (live) setLinks(d?.links?.[transactionId] || []) })
      .catch(() => { /* no phone link shown when the phone side cannot be read; the payment is unaffected */ })
    return () => { live = false }
  }, [ok, caseId, transactionId])
  if (!ok || !links.length) return null
  return (
    <div data-testid="phone-mentions" className="text-sm">
      {links.map((l) => (
        <p key={l.record_uid}>
          Also recorded on phone {l.phone_label}: {l.source}
          {l.instant ? ` at ${instantWords(l.instant, "UTC")}` : ""}.{" "}
          <Link className="underline" to={`/cases/${caseId}/records/${l.record_uid}`}>Open the phone record</Link>
          <span className="text-muted-foreground">{l.outcome === "near_amount" ? " The amounts differ slightly." : ""} A reading from the phone, not a statement.</span>
        </p>
      ))}
    </div>
  )
}
