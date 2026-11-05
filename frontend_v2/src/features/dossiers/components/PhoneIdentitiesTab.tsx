import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { getPhones } from "@/features/phones/api"
import { dayOf, peopleAPI, type RegistryItem } from "@/features/phones/people.api"
import { IdentityLinkGroup } from "@/features/phones/review/IdentityLinkGroup"
import { PeopleSuggestions } from "@/features/phones/review/PeopleSuggestions"

const PAGE = 50
const fmt = (n: number) => n.toLocaleString("en-US")
const conversationsHref = (caseId: string, key: string, phone?: string) =>
  `/cases/${encodeURIComponent(caseId)}/conversations?tab=people&people=${encodeURIComponent(key)}${phone ? `&phones=${encodeURIComponent(phone)}` : ""}`

/**
 * Phone identities (03 section 10.2): one row per identity, with each phone's own name for it, events per phone,
 * first and last contact and the linked person. A link is a person's decision and goes through the identity decision
 * path; a suggestion stays a suggestion until someone decides it. Counts equal Conversations for the link they open.
 */
export function PhoneIdentitiesTab({ caseId, canEdit, onOpenDossier }: { caseId: string; canEdit: boolean; onOpenDossier: (id: string) => void }) {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get("idq") ?? "")
  const phone = params.get("idphone") ?? ""
  const linked = params.get("idlinked") ?? ""
  const offset = Math.max(0, Number(params.get("idfrom")) || 0)
  const open = params.get("identity")
  const suggestions = params.get("idpanel") === "suggestions"
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }
  const phones = useQuery({ queryKey: ["phones", caseId], queryFn: () => getPhones(caseId) })
  const list = useQuery({
    queryKey: ["phone-identities", caseId, q.trim(), phone, linked, offset],
    queryFn: () => peopleAPI.registry(caseId, { q, phone: phone || undefined, linked: linked ? linked === "yes" : undefined, cursor: offset, limit: PAGE }),
    placeholderData: keepPreviousData,
  })
  const items = list.data?.items ?? []
  const total = list.data?.total ?? 0
  if (phones.data && phones.data.phones.length === 0) {
    return <EmptyState title="No phone in this case" description="Add a phone report from Evidence and its numbers, addresses and accounts appear here." />
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-4 py-3 sm:px-6">
          <Input
            aria-label="Search identities"
            className="h-8 min-w-56 flex-1 text-xs"
            placeholder="Search numbers, addresses, accounts and each phone's names…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              set({ idq: e.target.value || null, idfrom: null })
            }}
          />
          <select aria-label="Phone" className="h-8 rounded border bg-card px-2 text-xs" value={phone} onChange={(e) => set({ idphone: e.target.value || null, idfrom: null })}>
            <option value="">Every phone</option>
            {(phones.data?.phones ?? []).map((p) => (
              <option key={p.extraction_id} value={p.extraction_id}>{p.label}</option>
            ))}
          </select>
          <select aria-label="Linked to a person" className="h-8 rounded border bg-card px-2 text-xs" value={linked} onChange={(e) => set({ idlinked: e.target.value || null, idfrom: null })}>
            <option value="">Linked or not</option>
            <option value="yes">Linked to a person</option>
            <option value="no">Not linked</option>
          </select>
          <Button size="sm" variant="outline" aria-pressed={suggestions} onClick={() => set({ idpanel: suggestions ? null : "suggestions", identity: null })}>
            People suggestions
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4 sm:px-6">
          {list.isError && (
            <div role="alert" className="text-sm">
              <p>The identities could not be loaded.</p>
              <Button size="sm" variant="outline" className="mt-2" onClick={() => void list.refetch()}>Try again</Button>
            </div>
          )}
          {list.isLoading && <p role="status" className="text-sm">Loading the identities</p>}
          {list.data && (
            <>
              <p role="status" className="mb-2 text-xs text-muted-foreground">
                {total === 0 ? "No identity matches." : `Showing ${fmt(offset + 1)} to ${fmt(offset + items.length)} of ${fmt(total)} ${total === 1 ? "identity" : "identities"}, busiest first.`}{" "}
                {fmt(list.data.linked_in_case)} of {fmt(list.data.in_case)} in this case are linked to a person.
              </p>
              {items.length > 0 && (
                <table className="w-full text-left text-xs">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th scope="col" className="p-1.5">Identifier</th>
                      <th scope="col" className="p-1.5">Name on each phone</th>
                      <th scope="col" className="p-1.5">Messages and calls per phone</th>
                      <th scope="col" className="p-1.5">First contact</th>
                      <th scope="col" className="p-1.5">Last contact</th>
                      <th scope="col" className="p-1.5">Person</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((i) => (
                      <Row key={i.identity_key} caseId={caseId} item={i} open={open === i.identity_key}
                        onOpen={() => set({ identity: i.identity_key, idpanel: null })} onOpenDossier={onOpenDossier} />
                    ))}
                  </tbody>
                </table>
              )}
              {total > PAGE && (
                <div className="mt-3 flex items-center justify-between gap-2 text-xs">
                  <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => set({ idfrom: String(Math.max(0, offset - PAGE)) || null })}>Previous</Button>
                  <Button size="sm" variant="outline" disabled={list.data.next_cursor === null} onClick={() => set({ idfrom: String(list.data!.next_cursor) })}>Next</Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      {(open || suggestions) && (
        <aside aria-label={open ? "Identity" : "People suggestions"} className="w-full shrink-0 overflow-auto border-l border-border bg-background p-3 lg:w-[26rem]">
          <div className="mb-2 flex justify-end">
            <Button size="sm" variant="ghost" onClick={() => set({ identity: null, idpanel: null })}>Close</Button>
          </div>
          {open ? <IdentityLinkGroup key={open} caseId={caseId} identityKey={open} canEdit={canEdit} origin="dossier" /> : <PeopleSuggestions caseId={caseId} origin="dossier" />}
        </aside>
      )}
    </div>
  )
}

function Row({ caseId, item, open, onOpen, onOpenDossier }: { caseId: string; item: RegistryItem; open: boolean; onOpen: () => void; onOpenDossier: (id: string) => void }) {
  return (
    <tr className={open ? "border-t bg-muted" : "border-t"}>
      <td className="p-1.5 align-top">
        <button type="button" className="break-all text-left font-medium underline underline-offset-2" onClick={onOpen}>
          {item.value_display ?? item.identity_key}
        </button>
        <span className="block text-muted-foreground">{item.subkind ?? item.kind}</span>
      </td>
      <td className="p-1.5 align-top">
        {item.names.length ? item.names.map((n) => `${n.phone_label ?? "A phone"}: ${n.name}`).join("; ") : "No phone gives a name"}
      </td>
      <td className="p-1.5 align-top">
        {item.phones.length === 0 && "None"}
        {item.phones.map((p) => (
          <Link key={p.extraction_id} className="mr-2 inline-block underline underline-offset-2" to={conversationsHref(caseId, item.identity_key, p.extraction_id)}>
            {p.phone_label}: {fmt(p.events)}
          </Link>
        ))}
      </td>
      <td className="whitespace-nowrap p-1.5 align-top">{item.phones.length ? dayOf(item.first_contact) : "None"}</td>
      <td className="whitespace-nowrap p-1.5 align-top">{item.phones.length ? dayOf(item.last_contact) : "None"}</td>
      <td className="p-1.5 align-top">
        {item.person ? (
          <button type="button" className="text-left underline underline-offset-2" onClick={() => onOpenDossier(item.person!.id)}>
            {item.person.display_name ?? "A person"}
          </button>
        ) : (
          "Not linked"
        )}
      </td>
    </tr>
  )
}
