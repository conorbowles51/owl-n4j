import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
import {
  statementScope,
  type StatementScope,
} from "../lib/statement-scope-contract"
const schema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  statement_scopes: z.array(statementScope).max(100),
  revision: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .nullable(),
  saved_at: z.string().nullable(),
  applied: z.literal(false),
})
export function StatementDraftPanel({
  caseId,
  fileId,
  scopes,
  onLoad,
  disabled,
}: {
  caseId: string
  fileId: string
  scopes: StatementScope[]
  onLoad: (scopes: StatementScope[]) => void
  disabled: boolean
}) {
  const client = useQueryClient()
  const [loadedRevision, setLoadedRevision] = useState<string | null>(null)
  const key = ["financial-statement-draft", caseId, fileId]
  const url = candidateUrl(
    `candidate-sources/${encodeURIComponent(fileId)}/statement-draft`,
    caseId
  )
  const parse = (raw: unknown) => {
    const data = schema.parse(raw)
    assertCandidateScope(data, caseId)
    if (data.evidence_file_id !== fileId)
      throw Error("Saved controls belong to another document.")
    return data
  }
  const draft = useQuery({
    queryKey: key,
    queryFn: async () => parse(await fetchAPI<unknown>(url)),
    retry: false,
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (
        !draft.data ||
        (draft.data.revision !== null && loadedRevision !== draft.data.revision)
      )
        throw Error("Load saved controls before replacing them.")
      const saved = parse(
        await fetchAPI<unknown>(url, {
          method: "PUT",
          body: {
            expected_revision: draft.data.revision,
            statement_scopes: scopes,
          },
        })
      )
      if (
        JSON.stringify(saved.statement_scopes) !==
        JSON.stringify(scopes.map((value) => statementScope.parse(value)))
      )
        throw Error("Saved controls differ from the submitted draft.")
      return saved
    },
    onSuccess: (data) => {
      client.setQueryData(key, data)
      setLoadedRevision(data.revision)
    },
  })
  const unchanged =
    draft.data &&
    JSON.stringify(draft.data.statement_scopes) ===
      JSON.stringify(scopes.map((s) => statementScope.parse(s)))
  return (
    <section
      aria-label="Saved statement controls"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">Save statement controls</h3>
      <p>
        Save the statements added to this preview so you can return later. These
        are draft controls; source validation happens again before finalization.
        Edits still inside the statement editor are not included.
      </p>
      {draft.isPending ? (
        <p role="status">Loading saved controls…</p>
      ) : draft.isError ? (
        <p role="alert">Saved controls unavailable. {draft.error.message}</p>
      ) : (
        <>
          <p>
            {draft.data.statement_scopes.length} saved statements ·{" "}
            {unchanged ? "No unsaved changes" : "Unsaved statement controls"}
          </p>
          {draft.data.saved_at && (
            <p>Saved {new Date(draft.data.saved_at).toLocaleString()}</p>
          )}
          {draft.data.revision !== null &&
            loadedRevision !== draft.data.revision && (
              <p>
                Saved controls are available. Load them before replacing the
                saved draft.
              </p>
            )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={disabled || save.isPending || !draft.data.revision}
              onClick={() => {
                onLoad(draft.data.statement_scopes)
                setLoadedRevision(draft.data.revision)
                save.reset()
              }}
            >
              Load saved statement controls
            </Button>
            <Button
              disabled={
                disabled ||
                draft.isFetching ||
                save.isPending ||
                unchanged ||
                (draft.data.revision !== null &&
                  loadedRevision !== draft.data.revision)
              }
              onClick={() => save.mutate()}
            >
              Save statement controls to case
            </Button>
          </div>
        </>
      )}
      <Button
        variant="outline"
        disabled={draft.isFetching || save.isPending}
        onClick={() => {
          setLoadedRevision(null)
          save.reset()
          void draft.refetch()
        }}
      >
        Refresh saved controls
      </Button>
      {save.isPending && <p role="status">Saving statement controls…</p>}
      {save.isError && (
        <p role="alert">
          Statement controls were not saved. {save.error.message}
        </p>
      )}
      {save.isSuccess && (
        <p role="status">Statement controls saved to this case.</p>
      )}
    </section>
  )
}
