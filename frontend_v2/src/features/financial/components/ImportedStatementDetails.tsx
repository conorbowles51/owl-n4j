import { CurrencyOptions } from "./CurrencyOptions"
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { useInvestigationScope } from "../stores/investigation-scope"

const balance = z.object({
  amount_minor: z.string().nullable(),
  page: z.number().nullable(),
})
const response = z.object({
  case_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string(),
  account_id: z.string(),
  period_id: z.string().nullable(),
  revision: z.string(),
  currency: z.string().nullable(),
  balance_convention: z.enum(["asset_balance", "liability_owed"]),
  details: z.object({
    holder: z.string(),
    account_number: z.string(),
    institution: z.string(),
  }),
  pages: z.array(z.number()),
  balances: z.object({ opening: balance, closing: balance }),
})
type Details = z.infer<typeof response>
const roles = ["opening", "closing"] as const

export function ImportedStatementDetails({
  caseId,
  sourceId,
  withSource = false,
}: {
  caseId: string
  sourceId: string
  withSource?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)
  const query = useQuery({
    queryKey: ["imported-statement-details", caseId, sourceId],
    enabled: open,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const data = response.parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${sourceId}/details?case_id=${caseId}`
        )
      )
      if (data.case_id !== caseId || data.source_document_id !== sourceId)
        throw Error("The details do not belong to this statement.")
      return data
    },
  })
  return (
    <section
      aria-label="Saved account details and balances"
      className="rounded border p-3 space-y-3"
    >
      {!open ? (
        <>
          <Button
            variant="outline"
            onClick={() => {
              setOpen(true)
              setSaved(false)
            }}
          >
            Edit account and balances
          </Button>
          {saved && (
            <p role="status">
              Changes saved. The statement details and balance checks are
              updated.
            </p>
          )}
        </>
      ) : query.isPending ? (
        <p role="status">Loading saved details…</p>
      ) : query.isError ? (
        <>
          <p role="alert">{query.error.message}</p>
          <Button onClick={() => void query.refetch()}>
            Retry loading details
          </Button>
        </>
      ) : (
        <DetailsForm
          key={query.data.revision}
          data={query.data}
          withSource={withSource}
          onCancel={() => setOpen(false)}
          onSaved={() => {
            setSaved(true)
            setOpen(false)
          }}
        />
      )}
    </section>
  )
}

function DetailsForm({
  data,
  withSource,
  onCancel,
  onSaved,
}: {
  data: Details
  withSource: boolean
  onCancel: () => void
  onSaved: () => void
}) {
  const client = useQueryClient()
  const [scope, applyScope] = useInvestigationScope(data.case_id)
  const [details, setDetails] = useState(data.details)
  const [currency, setCurrency] = useState(data.currency || "")
  const initialAmount = (role: (typeof roles)[number]) =>
    data.balances[role].amount_minor === null
      ? ""
      : correctionMoney(data.balances[role].amount_minor!, data.currency || "").replace(
          ` ${data.currency}`,
          ""
        )
  const [amounts, setAmounts] = useState({
    opening: initialAmount("opening"),
    closing: initialAmount("closing"),
  })
  const [pages, setPages] = useState({
    opening: data.balances.opening.page || 0,
    closing: data.balances.closing.page || 0,
  })
  const [page, setPage] = useState(data.pages[0] || 1)
  const [error, setError] = useState("")
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      const changes: Record<
        string,
        { amount_minor: string | null; page?: number }
      > = {}
      for (const role of roles) {
        if (
          amounts[role] === initialAmount(role) &&
          pages[role] === (data.balances[role].page || 0)
        )
          continue
        const text = amounts[role].trim()
        const raw = text
          ? correctionMinor(text.replace(/^-/, ""), currency)
          : null
        if (text && (raw === null || !data.pages.includes(pages[role])))
          throw Error(`Enter a valid ${role} balance and select its PDF page.`)
        changes[role] = {
          amount_minor:
            raw === null
              ? null
              : text.startsWith("-") && raw !== "0"
                ? `-${raw}`
                : raw,
          ...(text ? { page: pages[role] } : {}),
        }
      }
      const result = response.parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${data.source_document_id}/details?case_id=${data.case_id}`,
          {
            method: "PUT",
            body: {
              expected_revision: data.revision,
              ...details,
              ...changes,
              ...(currency !== data.currency && currency ? { currency } : {}),
            },
          }
        )
      )
      if (
        result.case_id !== data.case_id ||
        result.source_document_id !== data.source_document_id
      )
        throw Error("The save response does not belong to this statement.")
      return result
    },
    onSuccess: (result) => {
      if (
        scope.accountId === data.account_id &&
        result.account_id !== data.account_id
      )
        applyScope({ ...scope, accountId: result.account_id })
      client.setQueryData(
        ["imported-statement-details", data.case_id, data.source_document_id],
        result
      )
      onSaved()
      void client.invalidateQueries()
    },
    onError: (failure) => setError(failure.message),
  })
  return (
    <div className={withSource ? "grid gap-4 lg:grid-cols-2" : "space-y-3"}>
      {withSource && (
        <div>
          <label className="text-sm">
            PDF page{" "}
            <select
              aria-label="Details PDF page"
              value={page}
              onChange={(event) => setPage(Number(event.target.value))}
              className="border rounded bg-background p-2"
            >
              {data.pages.map((number) => (
                <option key={number} value={number}>
                  {number}
                </option>
              ))}
            </select>
          </label>
          <TransactionSourceHighlight
            sourceDocumentId={data.evidence_file_id}
            locatorPayload={{ kind: "page_only", page }}
            wholePage
          />
        </div>
      )}
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          setError("")
          save.mutate()
        }}
      >
        <h3 className="font-semibold">
          Account details and statement balances
        </h3>
        <fieldset disabled={save.isPending} className="space-y-3">
          {(
            [
              ["holder", "Account holder"],
              ["account_number", "Account number"],
              ["institution", "Bank"],
            ] as const
          ).map(([field, label]) => (
            <label key={field} className="block text-sm">
              {label}
              <input
                aria-label={`Saved ${label.toLowerCase()}`}
                value={details[field]}
                onChange={(event) =>
                  setDetails({ ...details, [field]: event.target.value })
                }
                className="block w-full rounded border bg-background p-2"
              />
            </label>
          ))}
          <label className="block text-sm">
            Statement currency
            <select
              aria-label="Saved statement currency"
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              className="block w-full rounded border bg-background p-2"
            >
              {!currency && <option value="">Choose currency</option>}
              <CurrencyOptions />
            </select>
          </label>
          {currency !== data.currency && currency && (
            <p role="status" className="text-sm">
              All payments and balances in this statement will use {currency}.
              The numbers stay the same; no exchange-rate conversion is applied.
            </p>
          )}
          {currency && (
            <>
              <p className="text-sm">
                Balances in {currency}.{" "}
                {data.balance_convention === "liability_owed"
                  ? "Enter the amount owed as printed on the card statement."
                  : "Enter the balances printed on the statement."}{" "}
                Leave an unknown balance blank.
              </p>
              {roles.map((role) => (
                <div key={role} className="grid grid-cols-2 gap-2">
                  <label className="text-sm">
                    {role === "opening" ? "Opening balance" : "Closing balance"}
                    <input
                      aria-label={`Saved ${role} balance`}
                      inputMode="decimal"
                      value={amounts[role]}
                      onChange={(event) =>
                        setAmounts({ ...amounts, [role]: event.target.value })
                      }
                      className="block w-full rounded border bg-background p-2"
                    />
                  </label>
                  <label className="text-sm">
                    Printed on page
                    <select
                      aria-label={`${role} balance page`}
                      value={pages[role]}
                      onChange={(event) => {
                        const value = Number(event.target.value)
                        setPages({ ...pages, [role]: value })
                        if (value) setPage(value)
                      }}
                      className="block w-full rounded border bg-background p-2"
                    >
                      <option value={0}>Choose page</option>
                      {data.pages.map((number) => (
                        <option key={number} value={number}>
                          {number}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              ))}
            </>
          )}
          <p className="text-xs text-muted-foreground">
            Your payments stay in place. The original values and these changes
            remain in the statement history.
          </p>
          <div className="flex gap-2">
            <Button type="submit">
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </fieldset>
        {error && <p role="alert">{error} Your edits remain here.</p>}
      </form>
    </div>
  )
}
