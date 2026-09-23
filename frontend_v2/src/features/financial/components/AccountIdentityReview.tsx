import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
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
import { randomRequestId } from "@/lib/browser-crypto"
import { accountParties } from "../lib/account-parties"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialAccess } from "../hooks/use-financial-access"

const kinds = {
  account_number: "Account number",
  clabe: "CLABE",
  iban: "IBAN",
  customer_number: "Customer number",
  contract_number: "Contract number",
  holder_tax_id: "Holder tax ID",
}
type Identifier = { kind: keyof typeof kinds; value: string }
type EntityLink = { party_id: string; entity_key: string }
const identityReview = z
  .object({
    identifiers: z
      .array(
        z.object({
          kind: z.enum(
            Object.keys(kinds) as [
              keyof typeof kinds,
              ...(keyof typeof kinds)[],
            ]
          ),
          value: z.string(),
        })
      )
      .default([]),
    entity_links: z
      .array(z.object({ party_id: z.string().uuid(), entity_key: z.string() }))
      .default([]),
  })
  .passthrough()
const identityState = accountParties.extend({
  accounts: z.array(
    accountParties.shape.accounts.element.extend({
      identity_review: identityReview,
      referenced_only: z.boolean(),
    })
  ),
  identity_history: z.array(
    z.object({
      account_id: z.string(),
      reason: z.string(),
      actor: z.string(),
      recorded_at: z.string(),
    })
  ),
})
type Draft = {
  account: string
  newId: string
  bank: string
  holder: string
  currency: string
  identifiers: Identifier[]
  links: EntityLink[]
  basis: string
  source: string
  page: string
  reason: string
  revision: string | null
}

export function AccountIdentityReview({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          Review account identifiers and missing accounts
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl max-h-[90dvh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Account identity and case connections</DialogTitle>
          <DialogDescription>
            Record an account’s alternate identifiers, add an account referenced
            in evidence before its statements arrive, or connect a reviewed
            person or business to an existing case entity.
          </DialogDescription>
        </DialogHeader>
        {open && <IdentityEditor caseId={caseId} />}
      </DialogContent>
    </Dialog>
  )
}

function IdentityEditor({ caseId }: { caseId: string }) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient(),
    url = `/api/financial/account-identities?case_id=${caseId}`
  const [draft, setDraft] = useFinancialDraft<Draft>(
    caseId,
    "account-identities",
    {
      account: "",
      newId: randomRequestId(),
      bank: "",
      holder: "",
      currency: "",
      identifiers: [],
      links: [],
      basis: "investigator_knowledge",
      source: "",
      page: "",
      reason: "",
      revision: null,
    }
  )
  const [preview, setPreview] = useState(false),
    [saved, setSaved] = useState(false)
  const [entitySearch, setEntitySearch] = useState(""),
    [searchTerm, setSearchTerm] = useState(""),
    [party, setParty] = useState("")
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "account-identities"],
    queryFn: async () => {
      const result = identityState.parse(await fetchAPI(url))
      if (result.case_id !== caseId)
        throw Error("Account identities belong to another case.")
      return result
    },
  })
  const sources = useQuery({
    queryKey: ["financial-ledger", caseId, "account-parties"],
    queryFn: async () =>
      accountParties.parse(
        await fetchAPI(`/api/financial/account-parties?case_id=${caseId}`)
      ),
  })
  const graphStatus = useQuery({
    queryKey: ["financial-ledger", caseId, "identity-graph-status"],
    queryFn: () =>
      fetchAPI<{ status: string }>(
        `/api/financial/account-identities/graph-status?case_id=${caseId}`
      ),
    refetchInterval: 5000,
  })
  const entities = useQuery({
    queryKey: ["case-identity-entities", caseId, searchTerm],
    enabled: !!searchTerm,
    queryFn: async () =>
      z
        .object({
          nodes: z.array(
            z.object({
              key: z.string(),
              name: z.string().optional(),
              label: z.string().optional(),
              type: z.string().optional(),
            })
          ),
        })
        .parse(
          await fetchAPI(
            `/api/graph/search?case_id=${caseId}&q=${encodeURIComponent(searchTerm)}&limit=30`
          )
        ),
  })
  const state = query.data
  const stale = !!state && !!draft.revision && draft.revision !== state.revision
  const patch = (change: Partial<Draft>) => {
    setDraft((d) => ({
      ...d,
      ...change,
      revision: d.revision || state?.revision || null,
    }))
    setPreview(false)
    setSaved(false)
  }
  const current = state?.accounts.find((a) => a.id === draft.account)
  const isReference = draft.account === "new" || current?.referenced_only
  const save = useMutation({
    mutationFn: async () => {
      if (!preview || stale || !canEdit || !state)
        throw Error("Review the current account identity before saving.")
      const result = identityState.parse(
        await fetchAPI(url, {
          method: "POST",
          body: {
            account_id: draft.account === "new" ? draft.newId : draft.account,
            expected_revision: draft.revision || state.revision,
            identifiers: draft.identifiers,
            entity_links: draft.links,
            reference: isReference
              ? {
                  institution: draft.bank,
                  holder: draft.holder || null,
                  currency: draft.currency,
                }
              : null,
            basis: {
              basis: draft.basis,
              sources:
                draft.basis === "source"
                  ? [
                      {
                        source_document_id: draft.source,
                        page_number: Number(draft.page),
                      },
                    ]
                  : [],
            },
            reason: draft.reason,
          },
        })
      )
      if (result.case_id !== caseId)
        throw Error("The saved identity belongs to another case.")
      return result
    },
    onSuccess: async (result) => {
      setDraft((d) => ({
        ...d,
        account: d.account === "new" ? d.newId : d.account,
        revision: result.revision,
      }))
      setSaved(true)
      setPreview(false)
      await client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
      await client.invalidateQueries({
        queryKey: ["financial-account-references", caseId],
      })
    },
  })
  const sync = useMutation({
    mutationFn: () =>
      fetchAPI(
        `/api/financial/account-identities/sync-graph?case_id=${caseId}`,
        { method: "POST" }
      ),
    onSuccess: async () => {
      await graphStatus.refetch()
      await client.invalidateQueries({ queryKey: ["graph"] })
    },
  })
  return (
    <div className="space-y-3 text-sm">
      <p>
        Account and routing identifiers can support a match. Customer, contract
        and tax identifiers are retained as context and never merge accounts.
        Common ownership is reviewed separately.
      </p>
      <p>
        Case graph:{" "}
        {graphStatus.data?.status === "current"
          ? "Up to date with the reviewed identities."
          : graphStatus.data?.status === "unavailable" || graphStatus.error
            ? "Temporarily unavailable; saved decisions are retained and synchronization retries automatically."
            : "Updates automatically from saved decisions, usually within 30 seconds."}{" "}
        <a className="underline" href={`/cases/${caseId}/graph`}>
          Open case graph
        </a>
      </p>
      {canEdit && (
        <Button
          variant="outline"
          disabled={sync.isPending}
          onClick={() => sync.mutate()}
        >
          Update case graph now
        </Button>
      )}
      {sync.error && <p role="alert">{sync.error.message}</p>}
      {(query.error || sources.error) && (
        <p role="alert">{query.error?.message || sources.error?.message}</p>
      )}
      {saved && (
        <p role="status" className="rounded border p-3">
          Saved to this case. Identifiers are available for account-reference
          matching; ownership remains a separate reviewed decision. You can
          close this window and link the referenced account to its holder.
        </p>
      )}
      {stale && (
        <p role="alert">
          Account identities changed. Your draft is retained.{" "}
          <button
            className="underline"
            onClick={() => {
              setDraft((d) => ({ ...d, revision: state!.revision }))
              setPreview(false)
            }}
          >
            Review draft against latest accounts
          </button>
        </p>
      )}
      <fieldset disabled={!canEdit || save.isPending} className="space-y-3">
        <label className="block">
          Account to identify
          <select
            aria-label="Account to identify"
            className="block w-full rounded border bg-background p-2"
            value={draft.account}
            onChange={(e) => {
              const a = state?.accounts.find((a) => a.id === e.target.value)
              patch({
                account: e.target.value,
                identifiers: a?.identity_review.identifiers || [],
                links: a?.identity_review.entity_links || [],
                bank: a?.institution || "",
                holder: a?.holder_as_recorded || "",
                currency: a?.currency || "",
                newId: randomRequestId(),
                reason: "",
                basis: "investigator_knowledge",
                source: "",
                page: "",
              })
            }}
          >
            <option value="">Choose an account</option>
            <option value="new">
              Record an account with no statement imported
            </option>
            {state?.accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {[
                  a.holder_as_recorded,
                  a.institution,
                  a.identifier_as_printed,
                  a.currency,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                {a.referenced_only ? " · No statement imported" : ""}
              </option>
            ))}
          </select>
        </label>
        {isReference && (
          <div className="grid gap-3 sm:grid-cols-3">
            {(
              [
                ["bank", "Referenced bank"],
                ["holder", "Suggested holder"],
                ["currency", "Account currency"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  className="block w-full rounded border bg-background p-2"
                  value={draft[key]}
                  onChange={(e) =>
                    patch({
                      [key]:
                        key === "currency"
                          ? e.target.value.toUpperCase()
                          : e.target.value,
                    })
                  }
                />
              </label>
            ))}
            <p>
              No balance, payment or statement is created. Later imported
              statements are proposed as matches for review.
            </p>
          </div>
        )}
        <fieldset className="rounded border p-3 space-y-2">
          <legend>Identifiers for this account</legend>
          {draft.identifiers.map((item, index) => (
            <div key={index} className="flex flex-wrap gap-2">
              <select
                aria-label={`Identifier type ${index + 1}`}
                className="rounded border bg-background p-2"
                value={item.kind}
                onChange={(e) =>
                  patch({
                    identifiers: draft.identifiers.map((p, i) =>
                      i === index
                        ? { ...p, kind: e.target.value as Identifier["kind"] }
                        : p
                    ),
                  })
                }
              >
                {Object.entries(kinds).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
              <input
                aria-label={`Identifier value ${index + 1}`}
                className="min-w-0 flex-1 rounded border bg-background p-2"
                value={item.value}
                onChange={(e) =>
                  patch({
                    identifiers: draft.identifiers.map((p, i) =>
                      i === index ? { ...p, value: e.target.value } : p
                    ),
                  })
                }
              />
              <Button
                variant="outline"
                onClick={() =>
                  patch({
                    identifiers: draft.identifiers.filter(
                      (_, i) => i !== index
                    ),
                  })
                }
              >
                Remove identifier {index + 1}
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            onClick={() =>
              patch({
                identifiers: [
                  ...draft.identifiers,
                  { kind: "account_number", value: "" },
                ],
              })
            }
          >
            Add identifier
          </Button>
        </fieldset>
        <details className="rounded border p-3">
          <summary>
            Connect a reviewed person or business to another case entity
          </summary>
          <p>
            This records an explicit identity connection. It does not merge or
            overwrite graph entities.
          </p>
          {draft.links.map((link) => (
            <p key={link.party_id}>
              {state?.parties.find((p) => p.id === link.party_id)?.name} →{" "}
              {link.entity_key}{" "}
              <button
                className="underline"
                onClick={() =>
                  patch({ links: draft.links.filter((p) => p !== link) })
                }
              >
                Remove case connection
              </button>
            </p>
          ))}
          <label className="block">
            Reviewed person or business
            <select
              aria-label="Reviewed identity to connect"
              className="block w-full rounded border bg-background p-2"
              value={party}
              onChange={(e) => setParty(e.target.value)}
            >
              <option value="">Choose a reviewed identity</option>
              {state?.parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Find existing case entity
            <input
              className="block w-full rounded border bg-background p-2"
              value={entitySearch}
              onChange={(e) => setEntitySearch(e.target.value)}
            />
          </label>
          <Button
            variant="outline"
            disabled={!entitySearch.trim() || !party}
            onClick={() => setSearchTerm(entitySearch.trim())}
          >
            Search case entities
          </Button>
          {entities.error && <p role="alert">{entities.error.message}</p>}
          {entities.data?.nodes
            .filter(
              (n) =>
                !n.key.startsWith("financial-") && !n.key.startsWith("ACC-")
            )
            .map((n) => (
              <Button
                className="m-1"
                variant="outline"
                key={n.key}
                onClick={() =>
                  patch({
                    links: [
                      ...draft.links.filter((p) => p.party_id !== party),
                      { party_id: party, entity_key: n.key },
                    ],
                  })
                }
              >
                {n.name || n.label || n.key} · {n.type}
              </Button>
            ))}
        </details>
        <label className="block">
          Basis
          <select
            className="block rounded border bg-background p-2"
            value={draft.basis}
            onChange={(e) => patch({ basis: e.target.value })}
          >
            <option value="investigator_knowledge">
              Investigator knowledge
            </option>
            <option value="source">Statement evidence</option>
          </select>
        </label>
        {draft.basis === "source" && (
          <div className="flex flex-wrap gap-3">
            <label>
              Supporting statement
              <select
                className="block w-full rounded border bg-background p-2"
                value={draft.source}
                onChange={(e) => patch({ source: e.target.value, page: "" })}
              >
                <option value="">Choose source</option>
                {sources.data?.source_choices.map((s) => (
                  <option
                    key={s.source_document_id}
                    value={s.source_document_id}
                  >
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Source page
              <select
                className="block rounded border bg-background p-2"
                value={draft.page}
                onChange={(e) => patch({ page: e.target.value })}
              >
                <option value="">Choose page</option>
                {sources.data?.source_choices
                  .find((s) => s.source_document_id === draft.source)
                  ?.pages.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
              </select>
            </label>
          </div>
        )}
        <label className="block">
          Reason for identity decision
          <textarea
            className="block w-full rounded border bg-background p-2"
            value={draft.reason}
            onChange={(e) => patch({ reason: e.target.value })}
          />
        </label>
        <Button
          disabled={!draft.account || !draft.reason.trim() || stale}
          onClick={() => setPreview(true)}
        >
          Preview identity changes
        </Button>
        {preview && (
          <section
            aria-label="Account identity preview"
            className="rounded border p-3 space-y-2"
          >
            <p>
              {isReference
                ? "Save a referenced account without importing any payments."
                : "Save these reviewed identifiers; original statement details stay unchanged."}
            </p>
            {draft.identifiers.map((p, i) => (
              <p key={i}>
                {kinds[p.kind]}: {p.value}
              </p>
            ))}
            <p>
              {draft.links.length} reviewed connection(s) to existing case
              entities.
            </p>
            <p>{draft.reason}</p>
            <Button onClick={() => save.mutate()}>
              Save reviewed identity
            </Button>
          </section>
        )}
        {save.error && <p role="alert">{save.error.message}</p>}
      </fieldset>
      {state && (
        <details>
          <summary>
            Identity decision history (
            {
              state.identity_history.filter(
                (h) => h.account_id === draft.account
              ).length
            }
            )
          </summary>
          {state.identity_history
            .filter((h) => h.account_id === draft.account)
            .map((h, i) => (
              <p key={i}>
                {h.recorded_at} · {h.actor} · {h.reason}
              </p>
            ))}
        </details>
      )}
    </div>
  )
}
