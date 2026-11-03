import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, compareWords } from "./compare-words"

/** Approach 12, extraction comparison (05 section 15), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "For each pair of extractions in the case: whether they are of one device, and if so which records are in one and not the other, which were deleted between them, and how much of the difference each extraction's selection, decoder version and times account for. It does not say who deleted anything."

export default function ExtractionComparisonPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("extraction_comparison"), [])
  return (
    <ApproachLayout caseId={caseId} title="Two extractions of one phone" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-extraction-comparison" tabs={TABS} words={compareWords} origin="phone-extraction-comparison" testId="compare-result"
      collectLabel={(r) => compareWords(r).title} emptyWords="Nothing of this kind: the case holds one extraction, or no pair is shown to be one device." />
  )
}
