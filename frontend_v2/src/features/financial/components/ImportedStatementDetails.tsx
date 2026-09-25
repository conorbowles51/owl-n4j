import { CurrencyOptions } from "./CurrencyOptions"
import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { useInvestigationScope } from "../stores/investigation-scope"
import { useFinancialDraft } from "../stores/financial-drafts"
import { statementAssessment } from "../lib/statement-assessment"
import { StatementReconciliationSummary } from "./StatementReconciliationSummary"

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
    period_start: z.string().default(""),
    period_end: z.string().default(""),
  }),
  pages: z.array(z.number()),
  balances: z.object({ opening: balance, closing: balance }),
  has_payment_readings: z.boolean().optional(),
  admission: statementAssessment.optional(),
})
type Details = z.infer<typeof response>
const roles = ["opening", "closing"] as const

export function ImportedStatementDetails({
  caseId,
  sourceId,
  withSource = false,
  initiallyOpen = false,
  focusField,
}: {
  caseId: string
  sourceId: string
  withSource?: boolean
  initiallyOpen?: boolean
  focusField?: string
}) {
  const [open, setOpen] = useState(initiallyOpen)
  const [saved, setSaved] = useState(false)
  const query = useQuery({
    queryKey: ["imported-statement-details", caseId, sourceId],
    enabled: true,
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
          {query.data && (
            <div
              className="space-y-1 text-sm"
              aria-label="Current saved statement details"
            >
              <p>
                <strong>{query.data.details.holder || "Holder missing"}</strong>{" "}
                · {query.data.details.institution || "Bank missing"} ·{" "}
                {query.data.details.account_number || "Account number missing"}{" "}
                · {query.data.currency}
              </p>
              <p>
                {query.data.details.period_start || "Start date missing"} to{" "}
                {query.data.details.period_end || "End date missing"}
              </p>
              <p>
                Saved opening balance:{" "}
                {query.data.balances.opening.amount_minor === null
                  ? "Not recorded"
                  : correctionMoney(
                      query.data.balances.opening.amount_minor,
                      query.data.currency || ""
                    )}
                . Saved closing balance:{" "}
                {query.data.balances.closing.amount_minor === null
                  ? "Not recorded"
                  : correctionMoney(
                      query.data.balances.closing.amount_minor,
                      query.data.currency || ""
                    )}
                .
              </p>
            </div>
          )}
          <Button
            variant="outline"
            onClick={() => {
              setOpen(true)
              setSaved(false)
            }}
          >
            Edit account, dates, currency and balances
          </Button>
          {saved && (
            <p role="status">
              Changes saved. The statement details and balance checks are
              updated.
            </p>
          )}
          {query.data?.admission && (
            <div
              aria-label="Saved statement checks"
              className="space-y-2 text-sm"
            >
              <p className="font-medium">
                {query.data.admission.assessment_current === false
                  ? "Changes are saved; reconciliation needs updating."
                  : query.data.admission.can_import
                    ? query.data.admission.status === "confirmed_no_activity"
                      ? "No activity confirmed at the last save. No payments were added."
                      : "The statement reconciled at its last saved check."
                    : "Details are saved, but the statement still needs review."}
              </p>
              <StatementReconciliationSummary
                calculation={query.data.admission.calculation}
                controlBasis="saved"
                format={(value) =>
                  correctionMoney(value, query.data!.currency || "")
                }
              />
              {!query.data.admission.can_import && (
                <ul className="list-disc pl-5 space-y-1">
                  {query.data.admission.blockers.map((blocker, index) => (
                    <li key={index}>{blocker.message}</li>
                  ))}
                </ul>
              )}
            </div>
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
          focusField={focusField}
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
  focusField,
}: {
  data: Details
  withSource: boolean
  onCancel: () => void
  onSaved: () => void
  focusField?: string
}) {
  const form = useRef<HTMLFormElement>(null)
  useEffect(() => {
    const name = (
      {
        holder: "Saved account holder",
        account_number: "Saved account number",
        period: "Saved period start",
        currency: "Saved statement currency",
      } as Record<string, string>
    )[focusField || ""]
    if (!name) return
    const control = form.current?.querySelector<HTMLElement>(
      `[aria-label="${name}"]`
    )
    control?.focus({ preventScroll: true })
    control?.scrollIntoView({ block: "center" })
  }, [focusField])
  const client = useQueryClient()
  const [scope, applyScope] = useInvestigationScope(data.case_id)
  const initialAmount = (role: (typeof roles)[number]) =>
    data.balances[role].amount_minor === null
      ? ""
      : correctionMoney(
          data.balances[role].amount_minor!,
          data.currency || ""
        ).replace(` ${data.currency}`, "")
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    data.case_id,
    `statement-details:${data.source_document_id}`,
    {
      revision: data.revision,
      details: data.details,
      currency: data.currency || "",
      noActivityConfirmed: false,
      amounts: {
        opening: initialAmount("opening"),
        closing: initialAmount("closing"),
      },
      pages: {
        opening: data.balances.opening.page || 0,
        closing: data.balances.closing.page || 0,
      },
    }
  )
  const { details, currency, amounts, pages } = draft
  const setDetails = (details: Details["details"]) =>
    setDraft({ ...draft, details })
  const setCurrency = (currency: string) => setDraft({ ...draft, currency })
  const setAmounts = (amounts: typeof draft.amounts) =>
    setDraft({ ...draft, amounts })
  const setPages = (pages: typeof draft.pages) => setDraft({ ...draft, pages })
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
              expected_revision: draft.revision,
              ...details,
              ...changes,
              ...(draft.noActivityConfirmed
                ? { no_activity_confirmed: true }
                : {}),
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
      clearDraft()
      if (
        result.account_id !== data.account_id &&
        (scope.accountId === data.account_id ||
          scope.accountIds?.includes(data.account_id))
      )
        applyScope({
          ...scope,
          accountId:
            scope.accountId === data.account_id
              ? result.account_id
              : scope.accountId,
          accountIds: scope.accountIds?.map((id) =>
            id === data.account_id ? result.account_id : id
          ),
        })
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
        <div className="lg:sticky lg:top-3 lg:self-start">
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
        ref={form}
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          setError("")
          save.mutate()
        }}
      >
        <h3 className="font-semibold">
          Edit this statement's account, dates, currency and balances
        </h3>
        <p className="text-sm">
          Changes apply only to this statement period. Save changes to update
          the imported records; there is no need to import again.
        </p>
        {draft.revision !== data.revision && (
          <p role="alert">
            This statement changed while you were editing. Your draft is
            retained. Cancel to load the saved details before making a new
            correction.
          </p>
        )}
        <fieldset
          disabled={save.isPending}
          className="grid gap-3 sm:grid-cols-2"
        >
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
          <div className="grid grid-cols-2 gap-2 sm:col-span-2">
            {(
              [
                ["period_start", "Period start"],
                ["period_end", "Period end"],
              ] as const
            ).map(([field, label]) => (
              <label key={field} className="block text-sm">
                {label}
                <input
                  type="date"
                  aria-label={`Saved ${label.toLowerCase()}`}
                  value={details[field]}
                  onChange={(event) =>
                    setDetails({ ...details, [field]: event.target.value })
                  }
                  className="block w-full rounded border bg-background p-2"
                />
              </label>
            ))}
          </div>
          {data.has_payment_readings === false && (
            <label className="sm:col-span-2 flex items-start gap-2">
              <input
                type="checkbox"
                checked={draft.noActivityConfirmed || false}
                onChange={(e) =>
                  setDraft({ ...draft, noActivityConfirmed: e.target.checked })
                }
              />
              I checked every page of this period: there are no transactions.
              Confirm no activity if the saved balances reconcile.
            </label>
          )}
          <p className="text-xs text-muted-foreground sm:col-span-2">
            Leave unknown dates blank. These dates describe statement coverage;
            they do not change transaction dates.
          </p>
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
            <p role="status" className="text-sm sm:col-span-2">
              All payments and balances in this statement will use {currency}.
              The numbers stay the same; no exchange-rate conversion is applied.
            </p>
          )}
          {currency && (
            <>
              <p className="text-sm sm:col-span-2">
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
          <p className="text-xs text-muted-foreground sm:col-span-2">
            Your payments stay in place. The original values and these changes
            remain in the statement history.
          </p>
          <div className="flex gap-2 sm:col-span-2 sticky bottom-0 bg-background py-2">
            <Button type="submit">
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                clearDraft()
                onCancel()
              }}
            >
              Cancel
            </Button>
          </div>
        </fieldset>
        {error && <p role="alert">{error} Your edits remain here.</p>}
      </form>
    </div>
  )
}
