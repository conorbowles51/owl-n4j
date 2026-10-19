import { AccountIdentityReview } from "./AccountIdentityReview"
import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { accountParties, type AccountParties } from "../lib/account-parties"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialAccess } from "../hooks/use-financial-access"

type Link = AccountParties["accounts"][number]["relationships"][number]
const roles = {
  holder: "Account holder",
  controller: "Controller",
  signatory: "Authorised signatory",
  analysis_group: "Group for analysis",
}
type Draft = {
  accounts: string[]
  party: string
  name: string
  role: Link["role"]
  basis: Link["basis"]
  sources: Link["sources"]
  from: string
  to: string
  reason: string
  revision: string | null
  link: string | null
  remove: boolean
}

export function AccountOwnershipReview({
  caseId,
  accountIds = [],
  partyId,
  label = "Link accounts to a person or business",
  onChoose,
}: {
  caseId: string
  accountIds?: string[]
  partyId?: string
  label?: string
  onChoose?: (partyId: string) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">{label}</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Account ownership and relationships</DialogTitle>
          <DialogDescription>
            Review who holds each account. Saved links are available across
            Financial; the original statement names stay visible.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <OwnershipEditor
            caseId={caseId}
            accountIds={accountIds}
            partyId={partyId}
            onChoose={
              onChoose
                ? (id) => {
                    onChoose(id)
                    setOpen(false)
                  }
                : undefined
            }
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function OwnershipEditor({
  caseId,
  accountIds,
  partyId,
  onChoose,
}: {
  caseId: string
  accountIds: string[]
  partyId?: string
  onChoose?: (partyId: string) => void
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const form = useRef<HTMLFieldSetElement>(null)
  const [search, setSearch] = useState("")
  const [preview, setPreview] = useState(false)
  const [receipt, setReceipt] = useState<{
    party: string
    name: string
    count: number
    removed: boolean
  } | null>(null)
  const [draft, setDraft] = useFinancialDraft<Draft>(
    caseId,
    "reviewed-account-ownership",
    {
      accounts: accountIds,
      party: partyId || "new",
      name: "",
      role: "holder",
      basis: "investigator_knowledge",
      sources: [],
      from: "",
      to: "",
      reason: "",
      revision: null,
      link: null,
      remove: false,
    }
  )
  const key = ["financial-ledger", caseId, "account-parties"]
  const url = `/api/financial/account-parties?${new URLSearchParams({ case_id: caseId })}`
  const parse = (raw: unknown) => {
    const result = accountParties.parse(raw)
    if (result.case_id !== caseId)
      throw Error("These account links belong to another case.")
    return result
  }
  const query = useQuery({
    queryKey: key,
    queryFn: async () => parse(await fetchAPI(url)),
    retry: false,
  })
  const state = query.data
  const stale = !!state && !!draft.revision && draft.revision !== state.revision
  const patch = (values: Partial<Draft>) => {
    setDraft((current) => ({
      ...current,
      ...values,
      revision: current.revision ?? state?.revision ?? null,
    }))
    setPreview(false)
    setReceipt(null)
  }
  const focusForm = () =>
    requestAnimationFrame(() => {
      form.current?.scrollIntoView({ block: "start", behavior: "smooth" })
      form.current
        ?.querySelector<HTMLSelectElement>("select")
        ?.focus({ preventScroll: true })
    })
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!state || stale || !preview || !canEdit)
        throw Error("Review the current account links before saving.")
      const result = parse(
        await fetchAPI(url, {
          method: "POST",
          body: {
            expected_revision: draft.revision ?? state.revision,
            account_ids: draft.accounts,
            reason: draft.reason,
            ...(draft.remove
              ? { clear: true }
              : draft.party === "new"
                ? { new_party_name: draft.name }
                : { party_id: draft.party }),
            relationship: {
              id: draft.link,
              role: draft.role,
              basis: draft.basis,
              sources: draft.sources,
              effective_from: draft.from || null,
              effective_to: draft.to || null,
            },
          },
        })
      )
      if (!result.applied)
        throw Error(
          "The relationship save was not confirmed. Reload to check its history."
        )
      return result
    },
    onSuccess: async (result) => {
      const link = result.accounts
        .find((a) => a.id === draft.accounts[0])
        ?.relationships.find(
          (r) =>
            r.role === draft.role &&
            (draft.party === "new"
              ? r.party.name === draft.name.trim()
              : r.party.id === draft.party)
        )
      setReceipt({
        party: link?.party.id ?? draft.party,
        name: link?.party.name ?? draft.name,
        count: draft.accounts.length,
        removed: draft.remove,
      })
      client.setQueryData(key, result)
      setPreview(false)
      setDraft((current) => ({
        ...current,
        accounts: [],
        reason: "",
        name: "",
        party: "new",
        revision: null,
        link: null,
        remove: false,
        sources: [],
        from: "",
        to: "",
      }))
      await client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
  })
  const existingName = state?.parties.find(
    (p) =>
      p.name.trim().replace(/\s+/g, " ").toLocaleLowerCase() ===
      draft.name.trim().replace(/\s+/g, " ").toLocaleLowerCase()
  )
  const chosenName =
    draft.party === "new"
      ? draft.name.trim()
      : state?.parties.find((p) => p.id === draft.party)?.name
  const unavailable = draft.accounts.some(
    (id) => !state?.accounts.some((a) => a.id === id)
  )
  const valid =
    !!state &&
    !stale &&
    !unavailable &&
    draft.accounts.length > 0 &&
    draft.accounts.length <= 100 &&
    !!draft.reason.trim() &&
    (draft.remove ||
      (!!chosenName && !(draft.party === "new" && existingName))) &&
    !(draft.from && draft.to && draft.from > draft.to) &&
    (draft.basis !== "source" || draft.sources.length > 0)
  return (
    <div className="space-y-4 text-sm">
      <AccountIdentityReview caseId={caseId} />
      {query.isPending && (
        <p role="status">Loading accounts and saved relationships…</p>
      )}
      {query.error && <p role="alert">{query.error.message}</p>}
      <Button
        variant="outline"
        disabled={query.isFetching || save.isPending}
        onClick={() => {
          save.reset()
          void query.refetch()
        }}
      >
        Reload account relationships
      </Button>
      {receipt && (
        <div role="status" className="rounded border p-3 space-y-2">
          <p>
            {receipt.removed
              ? "Relationship removed"
              : `Relationship saved for ${receipt.count} ${receipt.count === 1 ? "account" : "accounts"}`}
            . Its reason and earlier decisions are retained in history.
          </p>
          {!receipt.removed && draft.role === "holder" && onChoose && (
            <Button onClick={() => onChoose(receipt.party)}>
              Show {receipt.name}’s accounts
            </Button>
          )}
        </div>
      )}
      {state && (
        <>
          <p>
            Accounts keep their own statements and balances. A holder link
            records reviewed ownership; control, signatory and analysis links do
            not. Leave dates blank when the period of the relationship is
            unspecified.
          </p>
          <details>
            <summary>
              Suggestions from statement headers (
              {state.ownership_review?.suggestions.length ?? 0})
            </summary>
            {state.ownership_review?.suggestions.map((s) => (
              <div key={s.id} className="rounded border p-3 my-2 space-y-2">
                <p>{s.reason}</p>
                {s.has_conflicting_links && (
                  <p>Existing account links differ; review them below.</p>
                )}
                {s.evidence.map((e, i) => (
                  <p key={i}>
                    {e.holder_as_recorded} · {e.printed_label} {e.printed_value}{" "}
                    · page {e.page_number}
                    {e.evidence_file_id && (
                      <>
                        {" "}
                        ·{" "}
                        <a
                          className="underline"
                          target="_blank"
                          rel="noreferrer"
                          href={`/api/evidence/${e.evidence_file_id}/file#page=${e.page_number}`}
                        >
                          Open source
                        </a>
                      </>
                    )}
                  </p>
                ))}
                <Button
                  disabled={!canEdit || save.isPending}
                  onClick={() => {
                    patch({
                      accounts: s.account_ids,
                      party: s.existing_party_id || "new",
                      name: s.suggested_name,
                      role: "holder",
                      basis: "source",
                      sources: [
                        ...new Map(
                          s.evidence.map((e) => [
                            `${e.source_document_id}:${e.page_number}`,
                            {
                              source_document_id: e.source_document_id,
                              page_number: e.page_number,
                            },
                          ])
                        ).values(),
                      ],
                      reason: s.reason,
                      from: "",
                      to: "",
                      link: null,
                      remove: false,
                    })
                    focusForm()
                  }}
                >
                  Review suggested ownership
                </Button>
              </div>
            ))}
            {state.ownership_review?.conflicts.map((c) => (
              <p key={c.account_id} role="alert">
                {c.reason}
              </p>
            ))}
          </details>
          <label className="block">
            Find an account
            <input
              className="block w-full rounded border bg-background p-2"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Holder, bank or account number"
            />
          </label>
          <div
            className="max-h-64 overflow-y-auto space-y-2"
            aria-label="Accounts and saved relationships"
          >
            {state.accounts
              .filter((a) =>
                [
                  a.holder_as_recorded,
                  a.institution,
                  a.identifier_as_printed,
                  a.currency,
                ]
                  .join(" ")
                  .toLowerCase()
                  .includes(search.toLowerCase())
              )
              .map((a) => (
                <div key={a.id} className="rounded border p-2 space-y-2">
                  <label>
                    <input
                      type="checkbox"
                      disabled={!canEdit || save.isPending || !!draft.link}
                      checked={draft.accounts.includes(a.id)}
                      onChange={(e) =>
                        patch({
                          accounts: e.target.checked
                            ? [...draft.accounts, a.id]
                            : draft.accounts.filter((id) => id !== a.id),
                        })
                      }
                    />{" "}
                    {[
                      a.holder_as_recorded || "Holder not recorded",
                      a.institution,
                      a.identifier_as_printed,
                      a.currency,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </label>
                  {a.party && (
                    <p className="text-muted-foreground">
                      Earlier analysis group: {a.party.name}. Ownership has not
                      been established by that grouping.
                    </p>
                  )}
                  {a.relationships.map((link) => (
                    <div key={link.id} className="ml-4 border-l pl-2">
                      <p>
                        {link.party.name} · {roles[link.role]} ·{" "}
                        {link.basis === "source"
                          ? "Statement evidence"
                          : "Investigator knowledge"}
                      </p>
                      <p>
                        {link.effective_from || "Start unspecified"} →{" "}
                        {link.effective_to || "End unspecified"}
                      </p>
                      {canEdit &&
                        [false, true].map((remove) => (
                          <Button
                            key={String(remove)}
                            variant="outline"
                            disabled={save.isPending}
                            onClick={() => {
                              patch({
                                accounts: [a.id],
                                party: link.party.id,
                                name: link.party.name,
                                role: link.role,
                                basis: link.basis,
                                sources: link.sources,
                                from: link.effective_from || "",
                                to: link.effective_to || "",
                                reason: "",
                                link: link.id,
                                remove,
                              })
                              focusForm()
                            }}
                          >
                            {remove ? "Remove link" : "Edit link"}
                          </Button>
                        ))}
                    </div>
                  ))}
                </div>
              ))}
          </div>
          {canEdit && (
            <fieldset
              ref={form}
              disabled={save.isPending}
              className="space-y-3 scroll-mt-4"
            >
              <legend className="font-semibold">
                {draft.remove
                  ? "Remove this relationship"
                  : "Review selected accounts"}{" "}
                · {draft.accounts.length} selected
              </legend>
              {!!draft.link && (
                <Button
                  variant="outline"
                  onClick={() =>
                    patch({
                      link: null,
                      remove: false,
                      accounts: [],
                      reason: "",
                    })
                  }
                >
                  Cancel this edit
                </Button>
              )}
              {!draft.remove && (
                <>
                  <label className="block">
                    Person or business
                    <select
                      className="block w-full rounded border bg-background p-2"
                      value={draft.party}
                      onChange={(e) => patch({ party: e.target.value })}
                    >
                      <option value="new">Create a person or business</option>
                      {state.parties.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {draft.party === "new" && (
                    <label className="block">
                      Name
                      <input
                        className="block w-full rounded border bg-background p-2"
                        maxLength={255}
                        value={draft.name}
                        onChange={(e) => patch({ name: e.target.value })}
                      />
                    </label>
                  )}
                  {draft.party === "new" && existingName && (
                    <p>
                      That name already exists.{" "}
                      <button
                        className="underline"
                        onClick={() => patch({ party: existingName.id })}
                      >
                        Use {existingName.name}
                      </button>
                    </p>
                  )}
                  <label className="block">
                    Relationship
                    <select
                      className="block w-full rounded border bg-background p-2"
                      value={draft.role}
                      onChange={(e) =>
                        patch({ role: e.target.value as Link["role"] })
                      }
                    >
                      {Object.entries(roles).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p>
                    Adding another holder preserves existing holders, including
                    joint ownership. To correct an existing link, choose Edit
                    link above.
                  </p>
                  <label className="block">
                    Basis
                    <select
                      className="block w-full rounded border bg-background p-2"
                      value={draft.basis}
                      onChange={(e) =>
                        patch({
                          basis: e.target.value as Link["basis"],
                          sources: [],
                        })
                      }
                    >
                      <option value="investigator_knowledge">
                        Investigator knowledge — explain below
                      </option>
                      <option value="source">
                        Statement evidence — choose pages
                      </option>
                    </select>
                  </label>
                  {draft.basis === "source" && (
                    <fieldset className="max-h-48 overflow-auto rounded border p-2">
                      <legend>Supporting statement pages</legend>
                      {state.source_choices
                        .filter(
                          (s) =>
                            !s.account_id ||
                            draft.accounts.includes(s.account_id)
                        )
                        .map((s) => (
                          <div key={s.source_document_id} className="my-2">
                            <p>
                              {s.label}
                              {s.evidence_file_id && (
                                <>
                                  {" "}
                                  ·{" "}
                                  <a
                                    className="underline"
                                    target="_blank"
                                    rel="noreferrer"
                                    href={`/api/evidence/${s.evidence_file_id}/file`}
                                  >
                                    Open statement
                                  </a>
                                </>
                              )}
                            </p>
                            {s.pages.map((page) => (
                              <label key={page} className="inline-block mr-3">
                                <input
                                  type="checkbox"
                                  checked={draft.sources.some(
                                    (c) =>
                                      c.source_document_id ===
                                        s.source_document_id &&
                                      c.page_number === page
                                  )}
                                  onChange={(e) =>
                                    patch({
                                      sources: e.target.checked
                                        ? [
                                            ...draft.sources,
                                            {
                                              source_document_id:
                                                s.source_document_id,
                                              page_number: page,
                                            },
                                          ]
                                        : draft.sources.filter(
                                            (c) =>
                                              c.source_document_id !==
                                                s.source_document_id ||
                                              c.page_number !== page
                                          ),
                                    })
                                  }
                                />{" "}
                                Page {page}
                              </label>
                            ))}
                          </div>
                        ))}
                      {!state.source_choices.length && (
                        <p>
                          No saved statement pages are available. Use
                          investigator knowledge and explain the evidence you
                          reviewed.
                        </p>
                      )}
                    </fieldset>
                  )}
                  <div className="flex flex-wrap gap-3">
                    <label>
                      Effective from (optional)
                      <input
                        type="date"
                        className="block rounded border bg-background p-2"
                        value={draft.from}
                        onChange={(e) => patch({ from: e.target.value })}
                      />
                    </label>
                    <label>
                      Effective to (optional)
                      <input
                        type="date"
                        className="block rounded border bg-background p-2"
                        value={draft.to}
                        onChange={(e) => patch({ to: e.target.value })}
                      />
                    </label>
                  </div>
                </>
              )}
              <label className="block">
                Reason and evidence reviewed
                <textarea
                  className="block w-full rounded border bg-background p-2"
                  maxLength={4000}
                  value={draft.reason}
                  onChange={(e) => patch({ reason: e.target.value })}
                />
              </label>
              {stale && (
                <div role="alert">
                  <p>
                    Account links changed while this draft was open. Your draft
                    is retained. Review the saved links above before continuing.
                  </p>
                  <Button
                    onClick={() => {
                      setDraft((d) => ({ ...d, revision: state.revision }))
                      setPreview(false)
                      save.reset()
                    }}
                  >
                    Use reviewed current links
                  </Button>
                </div>
              )}
              {unavailable && (
                <p role="alert">
                  A selected account is no longer available. Choose the current
                  accounts above.
                </p>
              )}
              {draft.from && draft.to && draft.from > draft.to && (
                <p role="alert">The end date must follow the start date.</p>
              )}
              {preview ? (
                <div
                  className="rounded border p-3 space-y-2"
                  aria-label="Relationship preview"
                >
                  <p>
                    {draft.remove ? "Remove" : draft.link ? "Update" : "Add"}{" "}
                    {roles[draft.role].toLowerCase()} link{" "}
                    {draft.remove ? "" : `for ${chosenName}`} on{" "}
                    {draft.accounts.length} accounts:
                  </p>
                  <ul>
                    {state.accounts
                      .filter((a) => draft.accounts.includes(a.id))
                      .map((a) => (
                        <li key={a.id}>
                          {a.institution} · {a.identifier_as_printed} ·{" "}
                          {a.currency}
                        </li>
                      ))}
                  </ul>
                  <p>
                    {draft.from || "Start unspecified"} →{" "}
                    {draft.to || "End unspecified"} ·{" "}
                    {draft.basis === "source"
                      ? `${draft.sources.length} source pages`
                      : "Investigator knowledge"}
                  </p>
                  <p>{draft.reason}</p>
                  <p>
                    The source names and payments stay unchanged.{" "}
                    {draft.role === "holder"
                      ? "Holder links appear in shared person filters and profiles; their dates remain visible for review."
                      : "This link will not be treated as account ownership."}
                  </p>
                  <Button
                    disabled={
                      !valid ||
                      save.isPending ||
                      query.isFetching ||
                      save.isError
                    }
                    onClick={() => save.mutate()}
                  >
                    {save.isPending
                      ? "Saving…"
                      : draft.remove
                        ? "Remove reviewed link"
                        : "Save reviewed relationship"}
                  </Button>
                  <Button variant="outline" onClick={() => setPreview(false)}>
                    Back to edit
                  </Button>
                </div>
              ) : (
                <Button
                  disabled={!valid || save.isPending || query.isFetching}
                  onClick={() => {
                    save.reset()
                    setPreview(true)
                  }}
                >
                  Review changes
                </Button>
              )}
              {save.error && (
                <p role="alert">
                  {save.error.message} Reload account relationships to check an
                  uncertain save before retrying.
                </p>
              )}
              <p className="text-muted-foreground">
                Unfinished edits stay in this browser tab. Save to share the
                relationship with the case.
              </p>
            </fieldset>
          )}
          <details>
            <summary>Relationship history ({state.history.length})</summary>
            {state.history.map((h) => (
              <div key={h.id} className="rounded border p-2 my-2">
                <p>
                  {
                    state.accounts.find((a) => a.id === h.account_id)
                      ?.identifier_as_printed
                  }{" "}
                  · {h.actor} · {h.recorded_at}
                </p>
                <p>{h.reason}</p>
                {h.after.relationships ? (
                  <p>
                    {h.after.relationships
                      .map((l) => `${l.party.name}: ${roles[l.role]}`)
                      .join("; ") || "No reviewed relationships remain"}
                  </p>
                ) : (
                  <p>Analysis group: {h.after.party?.name || "Removed"}</p>
                )}
              </div>
            ))}
          </details>
        </>
      )}
    </div>
  )
}
