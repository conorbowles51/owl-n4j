import { Link } from "react-router-dom"
import { cn } from "@/lib/cn"
import { useMentionMarks } from "./marks-store"
import { outcomeTone } from "./tones"

/**
 * The mark on a message that holds a checked mention, wherever the message is shown (Conversations, the workspace
 * list, Search). It opens the mention on the Mentions screen.
 */

export function MentionMark({ caseId, recordUid, className }: { caseId: string | undefined; recordUid: string | undefined; className?: string }) {
  const marks = useMentionMarks(caseId, recordUid)
  if (!caseId || !marks.length) return null
  return (
    <span className={cn("inline-flex flex-wrap gap-1", className)}>
      {marks.map((m) => (
        <Link
          key={m.id}
          to={`/cases/${encodeURIComponent(caseId)}/phones/mentions?mention=${encodeURIComponent(m.id)}`}
          onClick={(e) => e.stopPropagation()}
          className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium no-underline", outcomeTone(m.outcome))}
          title={`“${m.phrase}”${m.read_by ? ` · ${m.read_by}` : ""}`}
        >
          <span>{m.kind_label}</span>
          <span aria-hidden>·</span>
          <span>{m.outcome_label}</span>
        </Link>
      ))}
    </span>
  )
}
