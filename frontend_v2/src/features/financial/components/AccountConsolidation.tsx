import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
import { Button } from "@/components/ui/button"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { accountParties } from "../lib/account-parties"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { AccountOwnershipReview } from "./AccountOwnershipReview"

const account = accountParties.shape.accounts.element.extend({
  canonical_id: z.string(),
  payment_count: z.number(),
  periods: z.array(
    z.object({
      id: z.string(),
      source_document_id: z.string(),
      start: z.string().nullable(),
      end: z.string().nullable(),
      currency: z.string(),
    })
  ),
})
const state = z.object({
  case_id: z.string(),
  revision: z.string(),
  accounts: z.array(account),
  merges: z.array(
    z.object({
      id: z.string(),
      request_id: z.string(),
      retained_id: z.string(),
      account_ids: z.array(z.string()),
      undone: z.boolean(),
      actor: z.string().nullable(),
      reason: z.string(),
      recorded_at: z.string(),
    })
  ),
})
const preview = z.object({
  case_id: z.string(),
  revision: z.string(),
  retained_id: z.string(),
  accounts: z.array(account),
  payment_count: z.number(),
  explanation: z.string(),
  source_choices: accountParties.shape.source_choices,
})
const label = (a: z.infer<typeof account>) =>
  [a.holder_as_recorded, a.institution, a.identifier_as_printed, a.currency]
    .filter(Boolean)
    .join(" · ") || `Unidentified account ${a.id.slice(0, 8)}`

export function AccountConsolidation({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [proposal, setProposal] = useState<z.infer<typeof preview> | null>(null)
  const [source, setSource] = useState<{ file: string; page: number } | null>(
    null
  )
  const [notice, setNotice] = useState("")
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [draft, setDraft] = useFinancialDraft(caseId, "account-consolidation", {
    ids: [] as string[],
    retained: "",
    reason: "",
    request: randomRequestId(),
    undoRequest: randomRequestId(),
    revision: "",
  })
  const query = useQuery({
    queryKey: ["account-consolidation", caseId],
    enabled: open,
    retry: false,
    queryFn: async () => {
      const result = state.parse(
        await fetchAPI(
          `/api/financial/account-consolidations?case_id=${caseId}`
        )
      )
      if (result.case_id !== caseId)
        throw Error("The accounts belong to another case.")
      return result
    },
  })
  const change = (patch: Partial<typeof draft>) => {
    setDraft({ ...draft, ...patch, request: randomRequestId() })
    setProposal(null)
    setNotice("")
  }
  const parseState = (value: unknown) => {
    const result = state.parse(value)
    if (result.case_id !== caseId)
      throw Error("The result belongs to another case.")
    return result
  }
  const body = () => ({
    request_id: draft.request,
    expected_revision: query.data!.revision,
    account_ids: draft.ids,
    retained_id: draft.retained,
    reason: draft.reason,
  })
  const review = useMutation({
    mutationFn: async () =>
      preview.parse(
        await fetchAPI(
          `/api/financial/account-consolidations/preview?case_id=${caseId}`,
          { method: "POST", body: body() }
        )
      ),
    onSuccess: (p) => {
      if (p.case_id !== caseId) throw Error("Preview belongs to another case.")
      setProposal(p)
    },
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () =>
      parseState(
        await fetchAPI(
          `/api/financial/account-consolidations?case_id=${caseId}`,
          {
            method: "POST",
            body: { ...body(), expected_revision: proposal!.revision },
          }
        )
      ),
    onSuccess: async (result) => {
      client.setQueryData(["account-consolidation", caseId], result)
      setProposal(null)
      setNotice(
        "Accounts merged. Their original statements and payments remain available. Filters and profiles now use the retained account."
      )
      setDraft({
        ...draft,
        ids: [],
        retained: "",
        reason: "",
        request: randomRequestId(),
      })
      await client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(caseId),
      })
    },
  })
  const undo = useMutation({
    retry: false,
    mutationFn: async (mergeId: string) =>
      parseState(
        await fetchAPI(
          `/api/financial/account-consolidations/undo?case_id=${caseId}`,
          {
            method: "POST",
            body: {
              request_id: draft.undoRequest,
              expected_revision: query.data!.revision,
              merge_id: mergeId,
              reason: draft.reason,
            },
          }
        )
      ),
    onSuccess: async (result) => {
      client.setQueryData(["account-consolidation", caseId], result)
      setNotice(
        "Merge undone. Original accounts are separate again; payment and ownership decisions are retained."
      )
      setDraft({ ...draft, undoRequest: randomRequestId() })
      await client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(caseId),
      })
    },
  })
  const busy = review.isPending || save.isPending || undo.isPending
  const error = review.error || save.error || undo.error
  const shown = (query.data?.accounts ?? []).filter((a) =>
    label(a).toLowerCase().includes(search.toLowerCase())
  )
  return (
    <section
      className="space-y-3 rounded border p-3"
      aria-label="Review duplicate accounts"
    >
      <Button
        variant="outline"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        Merge duplicate accounts
      </Button>
      {open && (
        <>
          <p>
            Choose records for the same bank account. Different accounts owned
            by the same company should be linked to their common owner instead.
          </p>
          {query.isPending && (
            <p role="status">Loading accounts and statement history…</p>
          )}
          {query.isError && <p role="alert">{query.error.message}</p>}
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => {
              setProposal(null)
              void query.refetch()
            }}
          >
            Reload accounts and keep selection
          </Button>
          {query.data && (
            <fieldset disabled={busy || !canEdit} className="space-y-3">
              <label>
                Find accounts
                <input
                  className="block w-full rounded border p-2 bg-background"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              {!proposal && (
                <div className="max-h-80 overflow-auto space-y-2">
                  {shown.map((a) => (
                    <label
                      key={a.id}
                      className="flex items-start gap-2 rounded border p-2"
                    >
                      <input
                        type="checkbox"
                        checked={draft.ids.includes(a.id)}
                        onChange={(e) =>
                          change({
                            ids: e.target.checked
                              ? [...draft.ids, a.id]
                              : draft.ids.filter((id) => id !== a.id),
                          })
                        }
                      />
                      <span>
                        {label(a)}
                        <small className="block">
                          {a.payment_count} payments · {a.periods.length}{" "}
                          statement periods
                          {a.canonical_id !== a.id
                            ? " · already grouped with a retained account"
                            : ""}
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <label>
                Retain this account for display
                <select
                  className="block w-full rounded border p-2 bg-background"
                  value={draft.retained}
                  onChange={(e) => change({ retained: e.target.value })}
                >
                  <option value="">
                    Choose the account with correct details
                  </option>
                  {query.data.accounts
                    .filter((a) => draft.ids.includes(a.id))
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {label(a)}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Reason for merging or undoing
                <textarea
                  className="block w-full rounded border p-2 bg-background"
                  value={draft.reason}
                  onChange={(e) => change({ reason: e.target.value })}
                />
              </label>
              {proposal ? (
                <div className="space-y-3" aria-label="Account merge preview">
                  <p>{proposal.explanation}</p>
                  <div className="grid gap-2 lg:grid-cols-2">
                    {proposal.accounts.map((a) => (
                      <div key={a.id} className="rounded border p-3">
                        <strong>{label(a)}</strong>
                        <p>
                          {a.payment_count} payments · {a.relationships.length}{" "}
                          reviewed ownership or control links
                        </p>
                        {a.periods.map((p) => (
                          <p key={p.id}>
                            {p.start || "Date unknown"} –{" "}
                            {p.end || "Date unknown"} · {p.currency}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                  {proposal.source_choices.map(
                    (s) =>
                      s.evidence_file_id && (
                        <Button
                          key={s.source_document_id}
                          variant="outline"
                          onClick={() =>
                            setSource({
                              file: s.evidence_file_id!,
                              page: s.pages[0] || 1,
                            })
                          }
                        >
                          Review source: {s.label}
                        </Button>
                      )
                  )}
                  {source && (
                    <div
                      aria-label="Source for account comparison"
                      className="rounded border p-3"
                    >
                      <Button variant="ghost" onClick={() => setSource(null)}>
                        Close comparison source
                      </Button>
                      <TransactionSourceHighlight
                        sourceDocumentId={source.file}
                        locatorPayload={{
                          kind: "page_only",
                          page: source.page,
                        }}
                        wholePage
                      />
                    </div>
                  )}
                  <p>
                    {proposal.payment_count} payments retained. Currency totals
                    stay separate. Review overlapping statements and any earlier
                    transfers between these records.
                  </p>
                  <Button onClick={() => save.mutate()}>
                    Confirm merge of {proposal.accounts.length} account records
                  </Button>
                  <Button variant="outline" onClick={() => setProposal(null)}>
                    Back to selection
                  </Button>
                </div>
              ) : (
                <Button
                  disabled={
                    draft.ids.length < 2 ||
                    !draft.ids.includes(draft.retained) ||
                    !draft.reason.trim()
                  }
                  onClick={() => review.mutate()}
                >
                  Compare selected accounts
                </Button>
              )}
              {error && (
                <p role="alert">
                  {error.message} Your selection and reason are retained.
                </p>
              )}
              {notice && <p role="status">{notice}</p>}
              <details>
                <summary>Merge history and undo</summary>
                {query.data.merges
                  .filter((m) => !m.undone)
                  .map((m) => (
                    <div key={m.id} className="border rounded p-3">
                      <p>
                        {m.account_ids.length} account records · {m.actor} ·{" "}
                        {m.recorded_at}
                      </p>
                      <p>{m.reason}</p>
                      {query.data!.merges.some(
                        (u) => u.id === m.id && u.undone
                      ) ? (
                        <p>Undone</p>
                      ) : (
                        <>
                          <p>
                            Undo separates the original accounts. Later
                            payments, edits and identity links are retained.
                            Enter a reason above, then confirm.
                          </p>
                          <Button
                            variant="outline"
                            disabled={!draft.reason.trim()}
                            onClick={() => undo.mutate(m.id)}
                          >
                            Confirm undo of this merge
                          </Button>
                        </>
                      )}
                    </div>
                  ))}
                {!query.data.merges.length && (
                  <p>No account merges have been recorded.</p>
                )}
              </details>
            </fieldset>
          )}
          <AccountOwnershipReview
            caseId={caseId}
            accountIds={draft.ids}
            onChoose={() => void query.refetch()}
          />
        </>
      )}
    </section>
  )
}
