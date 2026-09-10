import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { counterpartyParties } from "../lib/counterparty-parties"
import { correctionMoney } from "../lib/correction-contract"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
export function CounterpartyPartyDirectory({ caseId }: { caseId: string }) {
  const client = useQueryClient(),
    key = ["financial-ledger", caseId, "counterparty-parties"]
  const [opened, setOpened] = useState(false),
    [selected, setSelected] = useState<string[]>([]),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(0),
    [historyPage, setHistoryPage] = useState(0),
    [party, setParty] = useState("new"),
    [name, setName] = useState(""),
    [reason, setReason] = useState(""),
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
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!query.data) throw Error("Reload identity links first.")
      const answer = parse(
        await fetchAPI(url, {
          method: "POST",
          body: {
            expected_revision: query.data.revision,
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
      if (
        !answer.applied ||
        !answer.event_ids?.length ||
        selected.some((id) => {
          const row = answer.readings.find((r) => r.transaction_id === id)
          return (
            !row ||
            (party === "clear"
              ? row.party !== null
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
      setSelected([])
      setReason("")
      setName("")
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
        r.party?.name ?? "",
      ].some((s) => s.toLocaleLowerCase().includes(needle))
    )
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
        Link explicitly selected readings to a reviewed party. Similar names and
        future imports are not joined automatically. These are identity
        decisions, not confirmation that a payment was made.
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
              setSelected([])
              void query.refetch()
            }}
          >
            Reload payment identities
          </Button>
          {query.isPending && <p>Loading payment identities…</p>}
          {query.error && <p role="alert">{query.error.message}</p>}
          {state && !query.isError && (
            <>
              <p>{state.limitation}</p>
              <label className="block">
                Find payment names, descriptions or references
                <input
                  aria-label="Find payment identities"
                  className="block w-full rounded border bg-background p-2"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(0)
                  }}
                />
              </label>
              <p>
                {rows.length} current readings; {selected.length} selected
                across pages (maximum100). Selection is independent of
                eligibility for totals.
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
                          checked={selected.includes(r.transaction_id)}
                          disabled={
                            !selected.includes(r.transaction_id) &&
                            selected.length >= 100
                          }
                          onChange={(e) =>
                            setSelected((v) =>
                              e.target.checked
                                ? [...v, r.transaction_id]
                                : v.filter((id) => id !== r.transaction_id)
                            )
                          }
                        />{" "}
                        {r.ref_id} ·{" "}
                        {r.counterparty_raw ?? "No counterparty name recorded"}{" "}
                        · {r.direction}{" "}
                        {correctionMoney(r.amount_minor, r.currency)}
                      </label>
                      <p className="break-words">{r.description}</p>
                      <p>
                        Reviewed party: {r.party?.name ?? "Unlinked"}
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
                  onClick={() => setPage(visiblePage - 1)}
                >
                  Previous identity readings
                </Button>
                <Button
                  disabled={(visiblePage + 1) * 25 >= rows.length}
                  onClick={() => setPage(visiblePage + 1)}
                >
                  Next identity readings
                </Button>
                <Button
                  disabled={!selected.length || save.isPending}
                  onClick={() => setSelected([])}
                >
                  Clear payment selection
                </Button>
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  save.mutate()
                }}
                className="space-y-2"
              >
                <fieldset disabled={save.isPending} className="space-y-2">
                  <label className="block">
                    Reviewed party
                    <select
                      aria-label="Payment party choice"
                      className="block w-full rounded border bg-background p-2"
                      value={party}
                      onChange={(e) => setParty(e.target.value)}
                    >
                      <option value="new">A new person or organisation</option>
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
                      Party name
                      <input
                        aria-label="Payment party name"
                        required
                        maxLength={255}
                        className="block w-full rounded border bg-background p-2"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </label>
                  )}
                  <label className="block">
                    Reason and supporting source interpretation
                    <textarea
                      aria-label="Payment identity reason"
                      required
                      maxLength={4000}
                      className="block w-full rounded border bg-background p-2"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  <Button
                    type="submit"
                    disabled={
                      !selected.length ||
                      !reason.trim() ||
                      (party === "new" && !name.trim()) ||
                      save.isPending
                    }
                  >
                    Save payment identity links
                  </Button>
                </fieldset>
              </form>
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
                          {state.readings.find(
                            (r) => r.transaction_id === h.transaction_id
                          )?.ref_id ?? h.transaction_id}
                        </p>
                        <p>
                          Direct link:{" "}
                          {h.before.party?.name ?? "No direct link"} →{" "}
                          {h.after.party?.name ??
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
