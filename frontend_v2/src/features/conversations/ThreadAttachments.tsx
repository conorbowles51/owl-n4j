import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { failureText, getThreadAttachments } from "@/features/phones/api"
import { fmt } from "@/features/phones/ui/count-sentence"

/**
 * The thread header's Attachments (N) and its counts (03 section 6.7, MD-1): N is the report's files the thread's
 * messages carried, the ones the Media grid scoped to the thread lists; the sentence counts every reference,
 * including the ones not in the report. Back to the stream returns to the message in focus when Media was opened.
 */
export function ThreadAttachments({ caseId, extraction, threadKey, title, back }: { caseId: string; extraction: string; threadKey: string; title: string; back: string }) {
  const q = useQuery({ queryKey: ["phone-thread-attachments", caseId, threadKey], queryFn: () => getThreadAttachments(caseId, threadKey), staleTime: 30_000 })
  if (q.isError) return <span role="alert" className="text-xs">{failureText(q.error, "The attachments could not be counted.")}</span>
  if (!q.data || q.data.referenced === 0) return null
  const to = `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/media?${new URLSearchParams({ thread: threadKey, thread_title: title, back }).toString()}`
  return (
    <span className="flex items-center gap-2 text-xs">
      {q.data.files > 0 ? (
        <Link className="rounded border px-2 py-0.5 underline-offset-2 hover:underline" to={to}>
          Attachments ({fmt(q.data.files)})
        </Link>
      ) : (
        <span className="text-muted-foreground">Attachments (0)</span>
      )}
      <span data-testid="thread-attachment-words">{q.data.words}</span>
    </span>
  )
}
