import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { failureText, getTranslations, translateMessage } from "../api"
import { translationKey } from "../lib/translation-key"
import type { StreamRow, Translation } from "../schemas"

const waiting = (t: Translation | null | undefined) => t?.state === "queued" || t?.state === "running"

/**
 * A message's machine translation (05 17.5), shown under the original, which the list prints first. Made on the
 * server by a local model, never replacing the message, always labelled as not checked by a person; a translation
 * of an earlier text of a corrected message says so. Text found to be English, or not recognised with confidence,
 * is not translated and says that instead.
 */
export function MessageTranslation({ caseId, row }: { caseId: string; row: StreamRow }) {
  const qc = useQueryClient()
  const key = translationKey(caseId, row.event_uid, row.body)
  const q = useQuery({
    queryKey: key,
    queryFn: async () => (await getTranslations(caseId, "message", [row.event_uid]))[row.event_uid] ?? null,
    initialData: row.translation ?? null,
    enabled: !!row.body && row.kind !== "call" && row.kind !== "record",
    staleTime: Infinity,
    refetchInterval: (query) => (waiting(query.state.data) ? 3000 : false),
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!row.body || row.kind === "call" || row.kind === "record") return null
  const t = q.data
  const ask = async () => {
    setBusy(true)
    setError(null)
    try {
      qc.setQueryData(key, await translateMessage(caseId, row.event_uid))
    } catch (e) {
      setError(failureText(e, e instanceof Error && e.message ? e.message : "The translation could not be asked for."))
    } finally {
      setBusy(false)
    }
  }
  const again = !t || t.state === "failed" || t.stale
  return (
    <div className="flex flex-col gap-0.5 text-xs" data-testid="message-translation">
      {t?.state === "queued" && <p role="status">Waiting to be translated on this server.</p>}
      {t?.state === "running" && <p role="status">Being translated now.</p>}
      {t?.state === "failed" && <p role="alert">{t.error}</p>}
      {t?.state === "done" && t.outcome === "translated" && (
        <div className={t.stale ? "border-l-2 border-status-review pl-2" : "border-l-2 pl-2"} aria-label="Machine translation">
          {t.stale && <p className="font-medium">{t.stale_words}</p>}
          <p className="whitespace-pre-wrap break-words text-sm">{t.text}</p>
          <p className="italic text-muted-foreground">{t.label}</p>
          {t.language_words && <p className="text-muted-foreground">{t.language_words}</p>}
        </div>
      )}
      {t?.state === "done" && t.outcome !== "translated" && (
        <p className="text-muted-foreground">
          {t.outcome_words} {t.language_words}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {again && (
        <Button size="sm" variant="link" className="h-auto self-start p-0 text-xs" disabled={busy} onClick={(e) => (e.stopPropagation(), void ask())}>
          {t?.stale ? "Translate the corrected text" : t?.state === "failed" ? "Try translating again" : "Translate"}
        </Button>
      )}
    </div>
  )
}
