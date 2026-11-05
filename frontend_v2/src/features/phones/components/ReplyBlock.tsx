import { Button } from "@/components/ui/button"
import { labelText } from "../lib/labels"
import { forwardWords, replyVerb, replyWhere } from "../lib/reply-words"
import type { ReplyLink, ReplyTarget, StreamRow } from "../schemas"

/**
 * Replies, quotes and forwards on a stream row (03 section 6.6, 07 section 4.4): a reply as an indented block linked
 * to its original, saying so when the original is not in the extraction; a forward marked as forwarded, with who
 * first wrote it kept apart from who sent this copy.
 */
export function ReplyBlock({ row, onGo }: { row: StreamRow; onGo?: (target: ReplyTarget, row: StreamRow) => void }) {
  const words = forwardWords(row)
  const replies = row.replies ?? []
  if (!words && !replies.length) return null
  return (
    <>
      {words && (
        <p className="text-xs font-medium text-muted-foreground" data-testid="forwarded">
          {words}.
        </p>
      )}
      {replies.map((r, k) => (
        <Original key={k} link={r} row={row} onGo={onGo} />
      ))}
    </>
  )
}

function Original({ link, row, onGo }: { link: ReplyLink; row: StreamRow; onGo?: (target: ReplyTarget, row: StreamRow) => void }) {
  const t = link.target
  return (
    <blockquote className="my-0.5 border-l-2 pl-2 text-xs text-muted-foreground" data-testid="reply-block" data-state={link.state}>
      {t ? (
        <>
          <span className="font-medium">
            {replyVerb(link)} {labelText(t.from)}, {t.time}
            {replyWhere(link)}
          </span>
          {t.flags.length > 0 && <span> [{t.flags.join(", ")}]</span>}
          <span className="line-clamp-2 whitespace-pre-wrap break-words">
            {t.excerpt ?? "(no text)"}
            {t.chars > (t.excerpt?.length ?? 0) ? "…" : ""}
          </span>
          {onGo && (
            <Button size="sm" variant="link" className="h-auto p-0 text-xs" onClick={() => onGo(t, row)}>
              Go to this message
            </Button>
          )}
        </>
      ) : link.state === "not_in_extraction" ? (
        <span title={`The report's id for it: ${link.original_id}`}>
          {replyVerb(link)} a message that is not in this extraction. The report gives its id: {link.original_id}.
        </span>
      ) : (
        <span>Marked as a reply. The report does not say to which message.</span>
      )}
    </blockquote>
  )
}
