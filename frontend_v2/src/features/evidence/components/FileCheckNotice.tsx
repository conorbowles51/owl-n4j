import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import type { EvidenceFile, EvidenceFileRecord } from "@/types/evidence.types"
import { evidenceAPI } from "../api"
import { holdText, mismatchText, scanText } from "../utils/file-check"

const BADGE = "ml-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
const WARNING = "border-amber-500/40 bg-amber-500/10 text-amber-700"

/** The marks a file's row carries: a name that does not match its contents, and a hold from reading. */
export function FileCheckBadges({ file }: { file: EvidenceFile | EvidenceFileRecord }) {
  const mismatch = mismatchText(file)
  return (
    <>
      {mismatch && <span title={mismatch} className={`${BADGE} ${WARNING}`}>Type mismatch</span>}
      {file.reading_hold === "held" && (
        <span
          title={holdText(file) ?? undefined}
          className={`${BADGE} border-destructive/40 bg-destructive/10 text-destructive`}
        >
          Held from reading
        </span>
      )}
    </>
  )
}

/** The same marks in words, above the file's preview, with the release a person makes. */
export function FileCheckNotice({ file, caseId }: { file: EvidenceFile; caseId: string }) {
  const queryClient = useQueryClient()
  const release = useMutation({
    mutationFn: () => evidenceAPI.releaseHold(file.id, caseId),
    onSuccess: () => {
      toast.success("Released for reading")
      void queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      void queryClient.invalidateQueries({ queryKey: ["evidence-file", file.id] })
      void queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
  const lines = [mismatchText(file), holdText(file), scanText(file)].filter(Boolean)
  if (!lines.length) return null
  return (
    <div role="status" className="mb-2 space-y-1 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
      {lines.map((line) => <p key={line}>{line}</p>)}
      {file.reading_hold === "held" && (
        <Button size="sm" variant="outline" disabled={release.isPending} onClick={() => release.mutate()}>
          Release for reading
        </Button>
      )}
    </div>
  )
}
