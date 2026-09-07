import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import {
  assertCandidateScope,
  candidateAccounts,
  candidateUrl,
} from "../lib/candidate-contract"

export type CandidateAccount = z.infer<
  typeof candidateAccounts
>["items"][number]
const resultSchema = z.object({
  case_id: z.string(),
  candidate_id: z.string(),
  evidence_file_id: z.string(),
  review_revision: z.string(),
  account: candidateAccounts.shape.items.element,
  applied: z.literal(false),
  created: z.boolean(),
  run_id: z.string(),
})
export function CandidateAccountForm({
  caseId,
  candidateId,
  fileId,
  reviewRevision,
  currency,
  disabled,
  onCreated,
  onBusy,
}: {
  caseId: string
  candidateId: string
  fileId: string
  reviewRevision: string
  currency: string
  disabled: boolean
  onCreated: (account: CandidateAccount) => void
  onBusy: (busy: boolean) => void
}) {
  const [opened, setOpened] = useState(false)
  const [label, setLabel] = useState("")
  const [reason, setReason] = useState("")
  const [blocked, setBlocked] = useState(false)
  const lock = useRef(false)
  const client = useQueryClient()
  const create = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = resultSchema.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `candidates/${encodeURIComponent(candidateId)}/provisional-account`,
            caseId
          ),
          {
            method: "POST",
            body: {
              label,
              reason,
              currency,
              expected_revision: reviewRevision,
            },
          }
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.candidate_id !== candidateId ||
        data.evidence_file_id !== fileId ||
        data.review_revision !== reviewRevision ||
        data.account.currency !== currency ||
        data.account.provisional !== true ||
        data.account.source_file_id !== fileId ||
        data.account.display_label !== label.trim()
      )
        throw new Error(
          "The returned account does not match this source and request. Reload the review."
        )
      return data.account
    },
    onSuccess: (account) => onCreated(account),
    onSettled: () => {
      setBlocked(true)
      onBusy(false)
      void client.invalidateQueries({
        queryKey: ["financial-candidates", caseId, "accounts"],
      })
    },
  })
  return (
    <div className="space-y-2 rounded border p-3">
      <Button
        variant="outline"
        disabled={disabled || create.isPending}
        onClick={() => setOpened((v) => !v)}
      >
        {opened ? "Hide provisional account" : "Set up a provisional account"}
      </Button>
      {opened && (
        <>
          <p>
            Use this when the account is not yet identified. Your label groups
            readings from this PDF in {currency || "the chosen currency"}; it is
            not a printed account number or verified identity. The same label in
            another PDF stays separate. Choose an existing account above when
            its identity is already established.
          </p>
          <fieldset
            disabled={disabled || blocked || create.isPending}
            className="space-y-2"
          >
            <label>
              Provisional account label
              <input
                aria-label="Provisional account label"
                className="block w-full rounded border bg-background p-2"
                value={label}
                maxLength={128}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Redacted card A"
              />
            </label>
            <label>
              Reason for provisional account
              <textarea
                aria-label="Reason for provisional account"
                className="block w-full rounded border bg-background p-2"
                value={reason}
                maxLength={4096}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <Button
              disabled={
                !label.trim() || !reason.trim() || !/^[A-Z]{3}$/.test(currency)
              }
              onClick={() => {
                if (lock.current || disabled || blocked) return
                lock.current = true
                onBusy(true)
                create.mutate()
              }}
            >
              Create provisional account
            </Button>
          </fieldset>
          {create.isError && (
            <p role="alert">
              Account creation could not be confirmed. {create.error.message}{" "}
              Reload the review before retrying.
            </p>
          )}
          {create.isSuccess && (
            <p role="status">
              Provisional account selected. Its creation and your reason are
              recorded; the reading still needs a review decision.
            </p>
          )}
        </>
      )}
    </div>
  )
}
