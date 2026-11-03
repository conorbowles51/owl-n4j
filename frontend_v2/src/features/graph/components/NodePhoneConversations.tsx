import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { getPersonCrossing } from "@/features/phones/api"

/**
 * XF-2 (07 section 7.2): from a person on the Graph to their messages and calls on the phones. The person's dossier
 * carries the phone numbers, addresses and accounts linked to them; the count is the one Conversations shows for the
 * link, which opens with those identities. Shown only when the case has phones linked to the person, or says why not.
 */
export function NodePhoneConversations({ caseId, entityKey }: { caseId: string; entityKey: string }) {
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ["graph-person-phones", caseId, entityKey],
    queryFn: () => getPersonCrossing(caseId, { entityKey }),
    enabled: !!caseId && !!entityKey && !entityKey.startsWith("phone-"),
    staleTime: 60_000,
  })
  if (!q.data || (q.data.state === "unlinked" && !q.data.people.length)) return null
  const d = q.data
  return (
    <section aria-label="Conversations on the phones" className="m-3 rounded border p-3 text-sm space-y-1">
      <p>{d.sentence}</p>
      {d.state === "linked" && d.conversations_href && (
        <Button size="sm" variant="outline" className="h-auto whitespace-normal text-left text-xs"
          onClick={() => navigate(d.conversations_href!)}>
          Conversations on the phones ({(d.total ?? 0).toLocaleString("en-US")})
        </Button>
      )}
    </section>
  )
}
