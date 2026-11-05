import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import {
  useAddFindingPayments,
  useCaseworkEntries,
} from "@/features/workspace/hooks/use-casework"
import {
  findingDraft,
  findingKindLabel,
  findingPaymentIds,
} from "../lib/investigator-finding"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"
import { SelectedPaymentsReview } from "./SelectedPaymentsReview"

const plural = (count: number) => (count === 1 ? "payment" : "payments")

/** Appends a person's selection to a saved finding. What the finding already cites stays exactly as saved. */
export function AddPaymentsToFinding({
  caseId,
  ids,
  entry,
  onClose,
}: {
  caseId: string
  ids: string[]
  entry?: CaseworkEntry
  onClose: () => void
}) {
  const [search, setSearch] = useState("")
  const [chosenId, setChosen] = useState(entry?.id ?? "")
  const [review, setReview] = useState(false)
  const query = useCaseworkEntries(entry ? undefined : caseId, {
    tag: "financial-workspace",
    q: search,
    limit: 25,
  })
  const found =
    query.data?.entries.filter((item) => item.case_id === caseId) ?? []
  const chosen = entry ?? found.find((item) => item.id === chosenId)
  const cited = new Set(chosen ? findingPaymentIds(chosen) : [])
  const fresh = ids.filter((id) => !cited.has(id))
  const add = useAddFindingPayments(caseId)
  const [, setFindingsView] = useFinancialDraft(caseId, "findings-list", {
    search: "",
    page: 0,
    kind: "financial",
    progress: "all",
    expanded: [] as string[],
  })
  const save = useMutation({
    retry: false,
    mutationFn: () => {
      if (!chosen || !fresh.length)
        throw Error("Choose a finding that does not already cite these payments.")
      return add.mutateAsync({
        entryId: chosen.id,
        input: { expected_version: chosen.version, transaction_ids: ids },
      })
    },
  })
  const open = () => {
    const saved = save.data?.entry
    if (!saved) return
    // The same finding reopens with its new payments, wherever it falls in the list.
    setFindingsView((current) => ({
      ...current,
      search: saved.title || "",
      page: 0,
      kind: "financial",
      progress: "all",
      expanded: [...new Set([...(current.expanded ?? []), saved.id])],
    }))
    useFinancialStore.getState().setMainView("findings")
    onClose()
  }
  return (
    <>
      <Dialog
        open={!review}
        onOpenChange={(value) => !value && !save.isPending && onClose()}
      >
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Add selected payments to a finding</DialogTitle>
            <DialogDescription>
              New payments are cited at their current values. What the finding
              already cites stays exactly as it was saved.
            </DialogDescription>
          </DialogHeader>
          {save.isSuccess ? (
            <div className="space-y-3" role="status">
              <p>
                {save.data.added} {plural(save.data.added)} added
                {save.data.already_cited > 0
                  ? `; ${save.data.already_cited} already cited`
                  : ""}
                . Earlier citations are unchanged.
              </p>
              <Button onClick={open}>Open this finding</Button>
              <Button variant="outline" onClick={onClose}>
                Return to investigation
              </Button>
            </div>
          ) : !ids.length ? (
            <div className="space-y-3">
              <p>
                No payments are selected. Select the payments on Transactions,
                then add them here.
              </p>
              <Button
                variant="outline"
                onClick={() => {
                  useFinancialStore.getState().setMainView("transactions")
                  onClose()
                }}
              >
                Go to Transactions
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {!entry && (
                <>
                  <label className="block">
                    Search findings and observations
                    <input
                      className="block w-full rounded border bg-background p-2"
                      aria-label="Search findings and observations"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </label>
                  {query.isPending && (
                    <p role="status">Loading saved findings…</p>
                  )}
                  {query.isError && (
                    <p role="alert">
                      Saved findings could not be loaded. {query.error.message}
                    </p>
                  )}
                  {!query.isPending && !query.isError && !found.length && (
                    <p>No saved finding or observation matches.</p>
                  )}
                  {found.length > 0 && (
                    <fieldset className="space-y-1 max-h-64 overflow-auto rounded border p-2">
                      <legend className="px-1 text-sm font-semibold">
                        Add to
                      </legend>
                      {found.map((item) => (
                        <label key={item.id} className="flex gap-2 items-start">
                          <input
                            type="radio"
                            name="finding"
                            className="mt-1"
                            checked={chosenId === item.id}
                            onChange={() => setChosen(item.id)}
                          />
                          <span className="min-w-0 break-words">
                            {findingKindLabel(findingDraft(item).kind)} ·{" "}
                            {item.title || "Untitled"} ·{" "}
                            {findingPaymentIds(item).length} supporting{" "}
                            {plural(findingPaymentIds(item).length)}
                          </span>
                        </label>
                      ))}
                      {(query.data?.total ?? 0) > found.length && (
                        <p className="text-sm text-muted-foreground">
                          Showing {found.length} of {query.data?.total}. Search
                          to find the others.
                        </p>
                      )}
                    </fieldset>
                  )}
                </>
              )}
              {chosen && (
                <div className="rounded border bg-muted/20 p-3 space-y-2">
                  <p className="font-medium break-words">
                    {chosen.title || "Untitled"}
                  </p>
                  <p>
                    {fresh.length} {plural(fresh.length)} to add
                    {ids.length > fresh.length
                      ? ` · ${ids.length - fresh.length} already cited and left as saved`
                      : ""}
                    {` · ${cited.size} cited now`}
                  </p>
                  {fresh.length > 0 && (
                    <Button variant="outline" onClick={() => setReview(true)}>
                      Review payments to add
                    </Button>
                  )}
                </div>
              )}
              <Button
                disabled={!chosen || !fresh.length || save.isPending}
                onClick={() => save.mutate()}
              >
                {save.isPending
                  ? "Adding payments…"
                  : `Add ${fresh.length} ${plural(fresh.length)}`}
              </Button>
            </div>
          )}
          {save.isError && (
            <p role="alert">
              {save.error.message} Reopen the finding to check what it cites
              before trying again.
            </p>
          )}
        </DialogContent>
      </Dialog>
      {review && (
        <SelectedPaymentsReview
          caseId={caseId}
          ids={fresh}
          onClose={() => setReview(false)}
        />
      )}
    </>
  )
}
