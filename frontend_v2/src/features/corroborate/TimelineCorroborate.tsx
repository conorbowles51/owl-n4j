import { CorroborateRows } from "./CorroborateRows"
import { rangeScope, rangeWords, type TimelineRange } from "./range-scope"

type Member = { type: string; id: string; label?: string }

export function TimelineCorroborate({ caseId, range, members }: { caseId: string; range: TimelineRange; members: Member[] }) {
  return (
    <CorroborateRows
      caseId={caseId}
      screen="the timeline"
      words={rangeWords(range)}
      count={members.length}
      scope={rangeScope(range)}
      read={async () => members}
    />
  )
}
