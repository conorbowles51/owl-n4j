import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, matrixWords } from "./matrix-words"

/** Approach 15, the from/to matrix (05 section 16b), as one row per pair and direction in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "Who contacts whom, in each direction: for each pair, the calls, messages and emails one sent or placed to the other, calls by whether they connected, and the count in the other direction beside it. A message held on both phones and matched counts once. It does not say why anyone was contacted."

export default function ContactMatrixPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("contact_matrix"), [])
  return (
    <ApproachLayout caseId={caseId} title="Who contacts whom" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-contact-matrix" tabs={TABS} words={matrixWords} origin="phone-contact-matrix" testId="matrix-result"
      collectLabel={(r) => matrixWords(r).title} emptyWords="No calls, messages or emails with a known sender and recipient on the phones." />
  )
}
