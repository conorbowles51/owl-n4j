import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { KindCounts } from "./KindCounts"
import { TABS, typedWords } from "./typed-words"

/**
 * Approach 7, what was typed (05 section 10), in the shared layout (05 3.9). Typed values are sensitive (05 3.8): the
 * server compares them and returns only the kind of term matched; the value is seen through the record's Reveal.
 */
export const WHAT_IT_DOES =
  "For each phone: the keyboard's learned words and the autofill values that match names, phone numbers, account endings, account holders or counterparties, people, organisations and other entities, amounts and places already in the case, and whether the same word occurs in the phone's messages, emails, notes, searches or calendar. It does not show who typed a word or when a learned word was typed."

export const NOT_INCLUDED =
  "Also compared: the case terms and the terms of the case's keyword lists, the names and aliases of the people, organisations and other entities in the case graph, the amounts in the case's ledger written the way the phone's region writes numbers (1,234.56 or 1.234,56; a whole amount only with its thousands separator, since a bare 1234 matched years and page numbers), and the case's addresses and place names."

export default function TypedWordsPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("typed_words"), [])
  return (
    <ApproachLayout caseId={caseId} title="Typed words" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-typed-words" tabs={TABS} words={typedWords} origin="phone-typed-words" testId="typed-result"
      collectLabel={(r) => typedWords(r).title} emptyWords="No learned word or autofill value on the phones matches the case's names, numbers, accounts, amounts or places."
      extra={<p className="text-sm text-muted-foreground">{NOT_INCLUDED}</p>} runExtra={(run) => <KindCounts run={run} />} />
  )
}
