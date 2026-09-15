import { useFinancialAccess } from "../hooks/use-financial-access"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { accountParties, type AccountParties } from "../lib/account-parties"
type AccountLinkDraft = {
  selected: string[]
  party: string
  name: string
  reason: string
  revision: string | null
}

export function AccountPartyDirectory({
  caseId,
  onChoose,
}: {
  caseId: string
  onChoose: (accountIds: string[], capture: AccountParties | null) => void
}) {
  const client = useQueryClient()
  const [draft, setDraft] = useFinancialDraft<AccountLinkDraft>(
    caseId,
    "account-identity-review",
    {
      selected: [],
      party: "new",
      name: "",
      reason: "",
      revision: null,
    }
  )
  const { selected, party, name, reason } = draft
  const url = `/api/financial/account-parties?${new URLSearchParams({ case_id: caseId })}`
  const key = ["financial-ledger", caseId, "account-parties"]
  const parse = (data: unknown) => {
    const result = accountParties.parse(data)
    if (result.case_id !== caseId)
      throw Error("Account links belong to another case.")
    return result
  }
  const query = useQuery({
    queryKey: key,
    queryFn: async () => parse(await fetchAPI(url)),
    retry: false,
  })
  const { canEdit } = useFinancialAccess()
  const updateReview = (
    patch:
      | Partial<AccountLinkDraft>
      | ((current: AccountLinkDraft) => Partial<AccountLinkDraft>)
  ) =>
    setDraft((current) => ({
      ...current,
      ...(typeof patch === "function" ? patch(current) : patch),
      revision: current.revision ?? query.data?.revision ?? null,
    }))
  const changedSinceDraft =
    !!query.data &&
    draft.revision !== null &&
    draft.revision !== query.data.revision
  const unavailableSelected =
    !!query.data &&
    selected.some(
      (id) => !query.data!.accounts.some((account) => account.id === id)
    )
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!query.data) throw Error("Reload the account links first.")
      if (changedSinceDraft)
        throw Error(
          "Account records or saved links changed. Review the latest records before saving this draft."
        )
      const answer = parse(
        await fetchAPI(url, {
          method: "POST",
          body: {
            expected_revision: draft.revision ?? query.data.revision,
            account_ids: selected,
            reason,
            ...(party === "new"
              ? { new_party_name: name }
              : party === "clear"
                ? { clear: true }
                : { party_id: party }),
          },
        })
      )
      if (
        !answer.applied ||
        selected.some((id) => {
          const account = answer.accounts.find((item) => item.id === id)
          return (
            !account ||
            (party === "clear"
              ? account.party !== null
              : party === "new"
                ? account.party?.name !== name.trim()
                : account.party?.id !== party)
          )
        })
      )
        throw Error("The account-link change was not confirmed.")
      return answer
    },
    onSuccess: async (data) => {
      client.setQueryData(key, data)
      setDraft((current) => ({
        ...current,
        selected: [],
        reason: "",
        name: "",
        revision: null,
      }))
      onChoose([], null)
      await client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
  })
  const state = query.data
  return (
    <section
      aria-label="Account party links"
      className="space-y-3 rounded border p-3"
    >
      <h4 className="font-medium">
        People and organisations linked to accounts
      </h4>
      <p>
        Save your reviewed account links with a reason. Original holder names
        and identifiers stay unchanged. Matching names alone do not establish
        identity.
      </p>
      <Button
        disabled={query.isFetching || save.isPending}
        onClick={() => {
          save.reset()
          void query.refetch()
        }}
      >
        Reload account links
      </Button>
      {query.isPending && <p>Loading account links…</p>}
      {query.error && <p role="alert">{query.error.message}</p>}
      {state && !query.isError && (
        <>
          <p className="text-sm text-muted-foreground">
            Unfinished account selections, the name and your explanation are
            kept in this browser tab after navigation or refresh. Save the links
            before closing the tab to share them with the case.
          </p>
          {changedSinceDraft && (
            <div role="alert" className="rounded border p-3 space-y-2">
              <p>
                Account records or saved links changed while this draft was
                open. Your selections and explanation are retained. Check the
                current account links below before using them to continue.
              </p>
              {canEdit && (
                <Button
                  disabled={query.isFetching || save.isPending}
                  onClick={() => {
                    setDraft((current) => ({
                      ...current,
                      revision: state.revision,
                    }))
                    save.reset()
                  }}
                >
                  Use latest account records
                </Button>
              )}
            </div>
          )}
          {unavailableSelected && (
            <p role="alert">
              Some selected accounts are no longer available. Clear the
              selection and choose the current accounts.
            </p>
          )}
          <div className="space-y-2">
            {state.parties.map((p) => {
              const ids = state.accounts
                .filter((a) => a.party?.id === p.id)
                .map((a) => a.id)
              return (
                <div key={p.id} className="flex flex-wrap items-center gap-2">
                  <span>
                    {p.name} · {ids.length} linked accounts
                  </span>
                  <Button
                    disabled={!ids.length || save.isPending}
                    onClick={() => onChoose(ids, state)}
                  >
                    Use {p.name} in this perspective
                  </Button>
                </div>
              )
            })}
            {!state.parties.length && <p>No party links have been recorded.</p>}
          </div>
          <fieldset
            disabled={!canEdit || save.isPending}
            className="max-h-72 space-y-2 overflow-y-auto"
          >
            <legend>Accounts to link or unlink</legend>
            {state.accounts.map((a) => (
              <label key={a.id} className="block rounded border p-2">
                <input
                  type="checkbox"
                  aria-label={`Select account ${a.id}`}
                  checked={selected.includes(a.id)}
                  onChange={(e) =>
                    updateReview((current) => ({
                      selected: e.target.checked
                        ? [...current.selected, a.id]
                        : current.selected.filter((id) => id !== a.id),
                    }))
                  }
                />{" "}
                {a.holder_as_recorded ?? "Holder not recorded"} ·{" "}
                {a.identifier_as_printed ?? a.id} ·{" "}
                {a.currency ?? "Currency not recorded"}
                <span className="block text-xs">
                  Recorded institution: {a.institution ?? "Unknown"}. Linked
                  party: {a.party?.name ?? "None"}.
                </span>
              </label>
            ))}
          </fieldset>
          {canEdit && (
            <Button
              variant="outline"
              disabled={!selected.length || save.isPending}
              onClick={() =>
                setDraft((current) => ({ ...current, selected: [] }))
              }
            >
              Clear account selection
            </Button>
          )}
          <label className="block">
            Link selected accounts to
            <select
              aria-label="Account party choice"
              className="ml-2 rounded border bg-background p-2"
              value={party}
              disabled={!canEdit || save.isPending}
              onChange={(e) => updateReview({ party: e.target.value })}
            >
              <option value="new">A new person or organisation</option>
              {state.parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              <option value="clear">Remove the existing links</option>
            </select>
          </label>
          {party === "new" && (
            <label className="block">
              Person or organisation name
              <input
                aria-label="New account party name"
                className="ml-2 rounded border bg-background p-2"
                maxLength={255}
                value={name}
                disabled={!canEdit || save.isPending}
                onChange={(e) => updateReview({ name: e.target.value })}
              />
            </label>
          )}
          <label className="block">
            Reason and supporting evidence
            <textarea
              aria-label="Account party link reason"
              className="block w-full rounded border bg-background p-2"
              maxLength={4000}
              value={reason}
              disabled={!canEdit || save.isPending}
              onChange={(e) => updateReview({ reason: e.target.value })}
            />
          </label>
          <Button
            disabled={
              !canEdit ||
              save.isPending ||
              save.isError ||
              query.isFetching ||
              changedSinceDraft ||
              unavailableSelected ||
              !selected.length ||
              selected.length > 100 ||
              !reason.trim() ||
              (party === "new" && !name.trim())
            }
            onClick={() => {
              if (canEdit) save.mutate()
            }}
          >
            Save account links
          </Button>
          {save.error && (
            <p role="alert">
              {save.error.message} Reload account links before retrying an
              uncertain result.
            </p>
          )}
          {save.isSuccess && (
            <p role="status">
              Account links saved with their decision history.
            </p>
          )}
          <details>
            <summary>
              Account link decision history ({state.history.length})
            </summary>
            {state.history.map((h) => (
              <div key={h.id} className="my-2 rounded border p-2 break-words">
                <p>
                  Account {h.account_id}, decision {h.sequence}:{" "}
                  {h.before.party?.name ?? "Unlinked"} →{" "}
                  {h.after.party?.name ?? "Unlinked"}
                </p>
                <p>{h.reason}</p>
                <p>
                  {h.actor} · {h.recorded_at}
                </p>
              </div>
            ))}
          </details>
        </>
      )}
    </section>
  )
}
