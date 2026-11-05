import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { HELP_PARAM, marksQuery, saveMark } from "../marks"

const SCREENS = [
  ["Phone summary", "What each phone holds, whose it is and what still needs a person."],
  ["Conversations", "Read messages and calls, by thread or by person, across all the phones."],
  ["Patterns", "A person's days, places and contacts over time, and whether two people were together."],
  ["Money on the phones", "Payments and amounts mentioned on the phones, beside the ledger."],
  ["Analyses", "Deleted material, relationships, shared contacts and other questions asked of the phones."],
  ["Needs a decision", "Readings and links that wait for a person to confirm them."],
] as const

/**
 * The one-time card (07 section 9): what each phone screen is for and where phone data appears elsewhere. Each person
 * sees it once, on any browser, and can reopen it from Help in the sidebar.
 */
export function FirstPhoneCard({ caseId }: { caseId: string }) {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const asked = params.has(HELP_PARAM)
  const marks = useQuery(marksQuery)
  const seen = useMutation({ mutationFn: () => saveMark("first_phone_card_seen"), onSuccess: (data) => client.setQueryData(marksQuery.queryKey, data) })
  // Kept open for this visit once shown, though saving "seen" changes the list it came from.
  const [firstTime, setFirstTime] = useState(false)
  const [closed, setClosed] = useState(false)
  if (marks.data && !marks.data.marks.first_phone_card_seen && !firstTime) setFirstTime(true)
  const save = seen.mutate
  useEffect(() => {
    if (firstTime) save()
  }, [firstTime, save])
  if (closed && !asked) return null
  if (!firstTime && !asked) return null
  const close = () => {
    setClosed(true)
    if (asked) setParams((p) => { p.delete(HELP_PARAM); return p }, { replace: true })
  }
  return (
    <section aria-label="What each phone screen is for" className="max-w-3xl rounded-lg border border-border bg-card p-4 text-sm">
      <h2 className="font-semibold">What each phone screen is for</h2>
      <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        {SCREENS.map(([name, words]) => (
          <div key={name} className="contents">
            <dt className="font-medium">{name}</dt>
            <dd>{words}</dd>
          </div>
        ))}
      </dl>
      <h3 className="mt-3 font-semibold">Where phone data appears elsewhere</h3>
      <p>
        The <Link className="underline" to={`/cases/${caseId}/timeline`}>Timeline</Link> and <Link className="underline" to={`/cases/${caseId}/map`}>Map</Link> can
        show phone entries as a layer, the <Link className="underline" to={`/cases/${caseId}/graph`}>Graph</Link> shows who was in contact with whom, Ctrl+K searches
        all of it, and anything can be added to a dossier or finding with Add to…
      </p>
      <p className="mt-2 text-muted-foreground">Help in the sidebar opens this again. The Guide button above each screen opens the guide at that screen.</p>
      <Button className="mt-2" size="sm" variant="outline" onClick={close}>Close</Button>
    </section>
  )
}
