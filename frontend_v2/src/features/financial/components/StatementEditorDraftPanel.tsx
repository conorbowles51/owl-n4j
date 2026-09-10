import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { controlCell, statementScope } from "../lib/statement-scope-contract"
export const editorDraft = z.object({
  group: z.string().max(128),
  selected: z.array(z.string().uuid()).max(1000),
  start: z.string().max(32),
  end: z.string().max(32),
  opening: z.string().max(128),
  closing: z.string().max(128),
  convention: z.enum(["", "asset_balance", "liability_owed"]),
  reason: z.string().max(4096),
  cells: z.object({
    start: controlCell.optional(),
    end: controlCell.optional(),
    opening: controlCell.optional(),
    closing: controlCell.optional(),
  }),
})
export type EditorDraft = z.infer<typeof editorDraft>
const envelope = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  revision: z.string().nullable(),
  statement_scopes: z.array(statementScope),
  editor_draft: editorDraft.nullable(),
  applied: z.literal(false),
})
export function StatementEditorDraftPanel({
  caseId,
  fileId,
  value,
  onLoad,
}: {
  caseId: string
  fileId: string
  value: EditorDraft
  onLoad: (value: EditorDraft) => void
}) {
  const client = useQueryClient(),
    key = ["financial-statement-draft", caseId, fileId, "editor"]
  const [loaded, setLoaded] = useState<string | null>(null)
  const url = candidateUrl(
    `candidate-sources/${encodeURIComponent(fileId)}/statement-draft`,
    caseId
  )
  const parse = (raw: unknown) => {
    const data = envelope.parse(raw)
    if (data.case_id !== caseId || data.evidence_file_id !== fileId)
      throw Error("Editor draft belongs to another source.")
    return data
  }
  const draft = useQuery({
    queryKey: key,
    retry: false,
    queryFn: async () => parse(await fetchAPI(url)),
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (
        !draft.data ||
        (draft.data.editor_draft && loaded !== draft.data.revision)
      )
        throw Error("Load the saved editor before replacing it.")
      const response = parse(
        await fetchAPI(url, {
          method: "PUT",
          body: {
            expected_revision: draft.data.revision,
            statement_scopes: draft.data.statement_scopes,
            editor_draft: editorDraft.parse(value),
          },
        })
      )
      if (
        JSON.stringify(response.editor_draft) !==
        JSON.stringify(editorDraft.parse(value))
      )
        throw Error("Saved editor differs from the submitted draft.")
      return response
    },
    onSuccess: (data) => {
      client.setQueryData(key, data)
      setLoaded(data.revision)
      void client.invalidateQueries({
        queryKey: ["financial-statement-draft", caseId, fileId],
        exact: true,
      })
    },
  })
  const valid = editorDraft.safeParse(value)
  return (
    <section
      aria-label="Save unfinished statement editor"
      className="space-y-2 rounded border p-3"
    >
      <p>
        Save these unfinished fields and selected source cells so you can reopen
        them later. They are not added to the preview or treated as reviewed
        statement controls.
      </p>
      {draft.isError && (
        <p role="alert">Editor draft unavailable. {draft.error.message}</p>
      )}
      {save.isError && (
        <p role="alert">Editor draft was not saved. {save.error.message}</p>
      )}
      {save.isSuccess &&
        JSON.stringify(draft.data?.editor_draft) ===
          JSON.stringify(valid.success ? valid.data : null) && (
          <p role="status">Unfinished editor saved.</p>
        )}
      {draft.data &&
        JSON.stringify(draft.data.editor_draft) !==
          JSON.stringify(valid.success ? valid.data : null) && (
          <p>Unsaved editor changes.</p>
        )}
      {draft.data?.editor_draft && (
        <Button
          variant="outline"
          disabled={save.isPending || draft.isFetching}
          onClick={() => {
            onLoad(draft.data!.editor_draft!)
            setLoaded(draft.data!.revision)
            save.reset()
          }}
        >
          Load unfinished statement editor
        </Button>
      )}
      <Button
        disabled={
          !valid.success ||
          !draft.data ||
          draft.isError ||
          draft.isFetching ||
          save.isPending ||
          !!(draft.data.editor_draft && loaded !== draft.data.revision)
        }
        onClick={() => save.mutate()}
      >
        Save unfinished statement editor
      </Button>
      <Button
        variant="outline"
        disabled={save.isPending || draft.isFetching}
        onClick={() => void draft.refetch()}
      >
        Refresh editor draft
      </Button>
    </section>
  )
}
