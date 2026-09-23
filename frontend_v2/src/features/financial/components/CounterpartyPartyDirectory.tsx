import { useFinancialAccess } from "../hooks/use-financial-access"
import { useFinancialDraft } from "../stores/financial-drafts"
import { PaymentIdentitySuggestions } from "./PaymentIdentitySuggestions"
import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { counterpartyParties } from "../lib/counterparty-parties"
import { correctionMoney } from "../lib/correction-contract"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
type IdentityDraft = {
  selected: string[]
  party: string
  name: string
  reason: string
  revision: string | null
  search: string
  page: number
}
export function CounterpartyPartyDirectory({ caseId }: { caseId: string }) {
  const client = useQueryClient(),
    key = ["financial-ledger", caseId, "counterparty-parties"]
  const [draft, setDraft] = useFinancialDraft<IdentityDraft>(
    caseId,
    "payment-identity-review",
    {
      selected: [],
      party: "new",
      name: "",
      reason: "",
      revision: null,
      search: "",
      page: 0,
    }
  )
  const { selected, party, name, reason, search, page } = draft
  const [opened, setOpened] = useState(false),
    [historyPage, setHistoryPage] = useState(0),
    [source, setSource] = useState<string | null>(null)
  const url = `/api/financial/counterparty-parties?${new URLSearchParams({ case_id: caseId })}`
  const parse = (data: unknown) => {
    const result = counterpartyParties.parse(data)
    if (result.case_id !== caseId)
      throw Error("Counterparty identities belong to another case.")
    return result
  }
  const query = useQuery({
    queryKey: key,
    enabled: opened,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => parse(await fetchAPI(url)),
  })
  const { canEdit } = useFinancialAccess()
  const updateReview = (
    patch:
      | Partial<IdentityDraft>
      | ((current: IdentityDraft) => Partial<IdentityDraft>)
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
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!query.data) throw Error("Reload identity links first.")
      if (changedSinceDraft)
        throw Error(
          "Payment records or saved links changed. Review the latest records before saving this draft."
        )
      const answer = parse(
        await fetchAPI(url, {
          method: "POST",
          body: {
            expected_revision: draft.revision ?? query.data.revision,
            transaction_ids: selected,
            reason,
            ...(party === "new"
              ? { new_party_name: name }
              : party === "clear"
                ? { clear: true }
                : { party_id: party }),
          },
        })
      )
      const confirmed = new Map(
        answer.readings.map((row) => [row.transaction_id, row])
      )
      if (
        !answer.applied ||
        !answer.event_ids?.length ||
        selected.some((id) => {
          const row = confirmed.get(id)
          return (
            !row ||
            (party === "clear"
              ? row.party !== null || !!row.account
              : party === "new"
                ? row.party?.name !== name.trim()
                : row.party?.id !== party)
          )
        })
      )
        throw Error(
          "Identity change was not confirmed. Reload before retrying."
        )
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
      await client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
    onError: async () => {
      // A lost response can follow a committed decision. Reload before the
      // retained draft can be retried against an older revision.
      await client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
  })
  const state = query.data,
    needle = search.toLocaleLowerCase(),
    rows = (state?.readings ?? []).filter((r) =>
      [
        r.ref_id,
        r.counterparty_raw ?? "",
        r.description ?? "",
        r.party?.name ?? r.account?.label ?? "",
      ].some((s) => s.toLocaleLowerCase().includes(needle))
    )
  const currentIds = new Set(
    state?.readings.map((row) => row.transaction_id) ?? []
  )
  const selectedIds = new Set(selected)
  const readingsById = new Map(
    state?.readings.map((row) => [row.transaction_id, row]) ?? []
  )
  const unavailableSelected = state
    ? selected.filter((id) => !currentIds.has(id))
    : []
  const safeHistoryPage = Math.min(
    historyPage,
    Math.max(0, Math.ceil((state?.history.length ?? 0) / 25) - 1)
  )
  const visiblePage = Math.min(
    page,
    Math.max(0, Math.ceil(rows.length / 25) - 1)
  )
  return (
    <section
      aria-label="Payment counterparty identity review"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">
        Review people and organisations on payments
      </h3>
      <p>
        Select payments you have checked against their statements, then link
        them to a person or business. You can combine their totals using Combine
        names I have linked to the same person or business above.
      </p>
      <Button variant="outline" onClick={() => setOpened((v) => !v)}>
        {opened
          ? "Hide payment identity review"
          : "Open payment identity review"}
      </Button>
      {opened && (
        <>
          <Button
            disabled={query.isFetching || save.isPending}
            onClick={() => {
              save.reset()
              void query.refetch()
            }}
          >
            Reload payment identities
          </Button>
          {query.isPending && <p>Loading payment identities…</p>}
          {query.error && <p role="alert">{query.error.message}</p>}
          {state && !query.isError && (
            <>
              <details>
                <summary>What linking payments changes</summary>
                <p>
                  Links apply to the selected payments. The printed names and
                  amounts stay unchanged. Future imports are not linked
                  automatically, and linking a name does not add excluded
                  payments to totals.
                </p>
              </details>
              {changedSinceDraft && (
                <div role="alert" className="rounded border p-3 space-y-2">
                  <p>
                    Payment records or saved links changed while this draft was
                    open. Your selections and explanation are retained. Check
                    the current links below before using them to continue.
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
                      Use latest payment records
                    </Button>
                  )}
                </div>
              )}
              {unavailableSelected.length > 0 && (
                <div role="alert" className="rounded border p-3 space-y-2">
                  <p>
                    {unavailableSelected.length} selected payments are no longer
                    current records. They may have been corrected. Inspect their
                    replacements in Transactions before linking them.
                  </p>
                  <Button
                    disabled={save.isPending || query.isFetching}
                    onClick={() =>
                      setDraft((current) => ({
                        ...current,
                        selected: current.selected.filter((id) =>
                          currentIds.has(id)
                        ),
                      }))
                    }
                  >
                    Remove unavailable payments from this selection
                  </Button>
                </div>
              )}
              <PaymentIdentitySuggestions
                readings={state.readings}
                disabled={save.isPending || query.isFetching}
                onSource={setSource}
                onSelect={(ids, partyId) => {
                  setDraft((current) => ({
                    ...current,
                    selected: ids,
                    party: partyId,
                    reason: "",
                    search: "",
                    page: 0,
                    revision: state.revision,
                  }))
                  save.reset()
                }}
              />
              <label className="block">
                Find payment names, descriptions or references
                <input
                  aria-label="Find payment identities"
                  className="block w-full rounded border bg-background p-2"
                  value={search}
                  onChange={(e) => {
                    setDraft((current) => ({
                      ...current,
                      search: e.target.value,
                      page: 0,
                    }))
                  }}
                />
              </label>
              <p>
                {rows.length} payment records match; {selected.length} selected
                across pages.
              </p>
              <Button
                variant="outline"
                disabled={!rows.length || save.isPending || query.isFetching}
                onClick={() =>
                  updateReview((current) => ({
                    selected: [
                      ...new Set([
                        ...current.selected,
                        ...rows.map((row) => row.transaction_id),
                      ]),
                    ],
                  }))
                }
              >
                Select all {rows.length} matching payments for linking
              </Button>
              <p className="text-sm text-muted-foreground">
                Unfinished selections, the name and your explanation are kept in
                this browser tab after navigation or refresh. Save the links
                before closing the tab to share them with the case.
              </p>
              <fieldset disabled={save.isPending} className="space-y-2">
                {rows
                  .slice(visiblePage * 25, visiblePage * 25 + 25)
                  .map((r) => (
                    <div key={r.transaction_id} className="rounded border p-2">
                      <label className="block">
                        <input
                          type="checkbox"
                          aria-label={`Link payment ${r.ref_id}`}
                          checked={selectedIds.has(r.transaction_id)}
                          onChange={(e) =>
                            updateReview((current) => ({
                              selected: e.target.checked
                                ? [...current.selected, r.transaction_id]
                                : current.selected.filter(
                                    (id) => id !== r.transaction_id
                                  ),
                            }))
                          }
                        />{" "}
                        {r.ref_id} ·{" "}
                        {r.counterparty_raw ?? "No counterparty name recorded"}{" "}
                        · {r.direction}{" "}
                        {correctionMoney(r.amount_minor, r.currency)}
                      </label>
                      <p className="break-words">{r.description}</p>
                      <p>
                        Linked counterparty:{" "}
                        {r.party?.name ?? r.account?.label ?? "Unlinked"}
                        {r.decision_transaction_id &&
                        r.decision_transaction_id !== r.transaction_id
                          ? " · retained from the original reading before correction"
                          : ""}
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setSource(r.transaction_id)}
                      >
                        Inspect identity source {r.ref_id}
                      </Button>
                    </div>
                  ))}
              </fieldset>
              <div className="flex gap-2">
                <Button
                  disabled={!visiblePage}
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      page: visiblePage - 1,
                    }))
                  }
                >
                  Previous identity readings
                </Button>
                <label>
                  Payment page{" "}
                  <select
                    aria-label="Payment identity page"
                    className="rounded border bg-background p-2"
                    value={visiblePage}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        page: Number(event.target.value),
                      }))
                    }
                  >
                    {Array.from(
                      { length: Math.max(1, Math.ceil(rows.length / 25)) },
                      (_, index) => (
                        <option key={index} value={index}>
                          {index + 1}
                        </option>
                      )
                    )}
                  </select>
                </label>
                <Button
                  disabled={(visiblePage + 1) * 25 >= rows.length}
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      page: visiblePage + 1,
                    }))
                  }
                >
                  Next identity readings
                </Button>
                <Button
                  disabled={!selected.length || save.isPending}
                  onClick={() =>
                    setDraft((current) => ({ ...current, selected: [] }))
                  }
                >
                  Clear payment selection
                </Button>
              </div>
              {canEdit && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    save.mutate()
                  }}
                  className="space-y-2"
                >
                  <fieldset disabled={save.isPending} className="space-y-2">
                    <label className="block">
                      Person or business
                      <select
                        aria-label="Payment party choice"
                        className="block w-full rounded border bg-background p-2"
                        value={party}
                        onChange={(e) =>
                          updateReview({ party: e.target.value })
                        }
                      >
                        <option value="new">
                          A new person or organisation
                        </option>
                        <option value="clear">Remove the selected links</option>
                        {state.parties.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {party === "new" && (
                      <label className="block">
                        Name
                        <input
                          aria-label="Payment party name"
                          required
                          maxLength={255}
                          className="block w-full rounded border bg-background p-2"
                          value={name}
                          onChange={(e) =>
                            updateReview({ name: e.target.value })
                          }
                        />
                      </label>
                    )}
                    <label className="block">
                      Why do these payments belong to this person or business?
                      <textarea
                        aria-label="Payment identity reason"
                        required
                        maxLength={4000}
                        className="block w-full rounded border bg-background p-2"
                        value={reason}
                        onChange={(e) =>
                          updateReview({ reason: e.target.value })
                        }
                      />
                    </label>
                    <Button
                      type="submit"
                      disabled={
                        !selected.length ||
                        !reason.trim() ||
                        (party === "new" && !name.trim()) ||
                        changedSinceDraft ||
                        unavailableSelected.length > 0 ||
                        query.isFetching ||
                        save.isPending
                      }
                    >
                      {save.isPending
                        ? `Saving links for ${selected.length} payments…`
                        : "Save payment identity links"}
                    </Button>
                  </fieldset>
                </form>
              )}
              {save.error && <p role="alert">{save.error.message}</p>}
              {save.isSuccess && (
                <p role="status">
                  Payment identity links saved with decision history.
                </p>
              )}
              <details>
                <summary>
                  Payment identity decision history ({state.history.length})
                </summary>
                <div className="max-h-80 space-y-2 overflow-auto">
                  <p>
                    History is ordered per reading. Page {safeHistoryPage + 1}{" "}
                    of {Math.max(1, Math.ceil(state.history.length / 25))}.
                  </p>
                  {state.history
                    .slice(safeHistoryPage * 25, safeHistoryPage * 25 + 25)
                    .map((h) => (
                      <article
                        key={h.id}
                        className="rounded border p-2 break-words"
                      >
                        <p>
                          Reading:{" "}
                          {readingsById.get(h.transaction_id)?.ref_id ??
                            h.transaction_id}
                        </p>
                        <p>
                          Direct link:{" "}
                          {h.before.party?.name ??
                            h.before.account?.label ??
                            "No direct link"}{" "}
                          →{" "}
                          {h.after.party?.name ??
                            h.after.account?.label ??
                            "Unlinked (overrides inheritance)"}
                        </p>
                        <p>{h.reason}</p>
                        <p>
                          {h.actor ?? "Recorded investigator"} · {h.recorded_at}
                        </p>
                        <Button
                          variant="outline"
                          onClick={() => setSource(h.transaction_id)}
                        >
                          Inspect identity decision source {h.sequence}
                        </Button>
                      </article>
                    ))}
                </div>
                <Button
                  variant="outline"
                  disabled={!safeHistoryPage}
                  onClick={() => setHistoryPage(safeHistoryPage - 1)}
                >
                  Previous identity decisions
                </Button>
                <Button
                  variant="outline"
                  disabled={(safeHistoryPage + 1) * 25 >= state.history.length}
                  onClick={() => setHistoryPage(safeHistoryPage + 1)}
                >
                  Next identity decisions
                </Button>
              </details>
            </>
          )}
        </>
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </section>
  )
}
