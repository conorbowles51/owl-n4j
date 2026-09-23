import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { accountParties } from "../lib/account-parties"

export type PaymentCounterpartyLink = { kind: "party" | "account"; id: string }

export function PaymentCounterpartyPicker({
  caseId,
  value,
  onChange,
  direction,
  disabled = false,
}: {
  caseId: string
  value?: PaymentCounterpartyLink | null
  onChange: (value: PaymentCounterpartyLink | null) => void
  direction?: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const query = useQuery({
    queryKey: ["payment-counterparty-choices", caseId],
    enabled: open || !!value,
    retry: false,
    staleTime: 0,
    queryFn: async () => {
      const result = accountParties.parse(
        await fetchAPI(`/api/financial/account-parties?case_id=${caseId}`)
      )
      if (result.case_id !== caseId)
        throw Error("The counterparty list belongs to another case.")
      return result
    },
  })
  const choices = [
    ...(query.data?.parties ?? []).map((p) => ({
      kind: "party" as const,
      id: p.id,
      label: p.name,
      type: "Person or business",
    })),
    ...(query.data?.accounts ?? [])
      .filter(
        (a) => !a.canonical_id || a.canonical_id === a.id || a.id === value?.id
      )
      .map((a) => ({
        kind: "account" as const,
        id: a.id,
        label:
          [
            a.holder_as_recorded,
            a.institution,
            a.identifier_as_printed,
            a.currency,
          ]
            .filter(Boolean)
            .join(" · ") || `Account ${a.id.slice(0, 8)}`,
        type: "Bank account",
      })),
  ]
  const selected = choices.find(
    (c) => c.id === value?.id && c.kind === value.kind
  )
  const filtered = choices.filter((c) =>
    c.label.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
  )
  return (
    <div className="mt-2 space-y-2 text-sm">
      <Button
        size="sm"
        variant="outline"
        type="button"
        disabled={disabled}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {value
          ? `Linked: ${selected?.label || "Loading identity…"}`
          : "Link existing person or account"}
      </Button>
      {value && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={() => onChange(null)}
        >
          Remove link
        </Button>
      )}
      {open && (
        <div className="rounded border p-2 space-y-2 bg-background">
          <p>
            {direction === "credit"
              ? "Paid by"
              : direction === "debit"
                ? "Paid to"
                : "Counterparty"}
            : choose from this case. The printed name is retained.
          </p>
          {!direction && (
            <p>
              For bank accounts, credits are paid by the counterparty; debits
              are paid to the counterparty. Card statements retain their charge
              and credit meanings.
            </p>
          )}
          <input
            aria-label="Search existing counterparties"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name, bank or account number"
            className="w-full border rounded p-2 bg-background"
          />
          {query.isPending && <p role="status">Loading people and accounts…</p>}
          {query.isError && (
            <p role="alert">
              {query.error.message}{" "}
              <Button type="button" onClick={() => void query.refetch()}>
                Retry loading choices
              </Button>
            </p>
          )}
          {query.isSuccess && (
            <div
              className="max-h-52 overflow-y-auto"
              aria-label="Existing counterparties"
            >
              {filtered.length === 0 && (
                <p>
                  No matching identities. You can keep the printed name without
                  a link.
                </p>
              )}
              {filtered.map((c) => (
                <button
                  type="button"
                  key={`${c.kind}:${c.id}`}
                  disabled={disabled}
                  className="block text-left w-full rounded p-2 hover:bg-muted"
                  onClick={() => {
                    onChange({ kind: c.kind, id: c.id })
                    setOpen(false)
                  }}
                >
                  <span className="text-xs text-muted-foreground">
                    {c.type}
                  </span>{" "}
                  · {c.label}
                </button>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Linking identifies the other side. Review related payments
            separately to confirm a transfer between accounts.
          </p>
        </div>
      )}
    </div>
  )
}
