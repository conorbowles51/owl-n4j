import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { CurrencyOptions } from "./CurrencyOptions"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { LedgerPanel } from "./LedgerPanel"
import { useFinancialDraft } from "../stores/financial-drafts"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"

const details = z.object({
  holder: z.string(),
  account_number: z.string(),
  institution: z.string(),
  period_start: z.string(),
  period_end: z.string(),
})
const response = z.object({
  case_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string(),
  recovery_revision: z.string(),
  details,
  currency: z.string().nullable(),
  pages: z.array(z.number()),
  transactions: z.array(
    z.object({
      key: z.string(),
      description: z.string().nullable(),
      ordering_date: z.string(),
      amount_minor: z.string(),
      currency: z.string(),
      direction: z.string(),
      page: z.number().nullable(),
    })
  ),
  incomplete_records: z.array(
    z
      .object({
        id: z.string(),
        fields: z.object({ description: z.string().optional() }).passthrough(),
      })
      .passthrough()
  ),
})
type Data = z.infer<typeof response>
type Section = z.infer<typeof details> & {
  key: string
  currency: string
  opening: string
  closing: string
  openingPage: number
  closingPage: number
}
const summary = z.object({
  key: z.string(),
  holder: z.string(),
  account_number: z.string(),
  currency: z.string(),
  transaction_count: z.number(),
  incomplete_count: z.number(),
  credit_minor: z.string(),
  debit_minor: z.string(),
})
const previewSchema = z.object({
  revision: z.string(),
  explanation: z.string(),
  transaction_count: z.number(),
  sections: z.array(summary),
})
const receiptSchema = z.object({
  applied: z.literal(true),
  source_document_id: z.string(),
  sections: z.array(
    z.object({
      key: z.string(),
      source_document_id: z.string(),
      currency: z.string(),
      transaction_count: z.number(),
    })
  ),
})

export function SavedStatementRecovery({
  caseId,
  sourceId,
}: {
  caseId: string
  sourceId: string
}) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ["saved-statement-recovery", caseId, sourceId],
    enabled: open,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const data = response.parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${sourceId}/recovery?case_id=${caseId}`
        )
      )
      if (data.case_id !== caseId || data.source_document_id !== sourceId)
        throw Error("The saved records belong to a different statement.")
      return data
    },
  })
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Separate account or currency sections
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="w-[calc(100vw-2rem)] max-w-none sm:max-w-[1500px] max-h-[92dvh] flex flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle>
              Separate this saved statement into its printed sections
            </DialogTitle>
            <DialogDescription>
              Check the original PDF, enter each account and currency, then
              assign every saved payment once. Review the complete change before
              saving.
            </DialogDescription>
          </DialogHeader>
          {query.isPending ? (
            <p role="status">Loading saved records…</p>
          ) : query.isError ? (
            <div>
              <p role="alert">{query.error.message}</p>
              <Button onClick={() => void query.refetch()}>
                Reload saved records
              </Button>
            </div>
          ) : (
            <RecoveryForm
              data={query.data}
              onReload={() => void query.refetch()}
              onClose={() => setOpen(false)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function RecoveryForm({
  data,
  onClose,
  onReload,
}: {
  data: Data
  onClose: () => void
  onReload: () => void
}) {
  const makeSection = (key: string): Section => ({
    ...data.details,
    key,
    currency: data.currency || "",
    opening: "",
    closing: "",
    openingPage: data.pages[0] || 1,
    closingPage: data.pages[0] || 1,
  })
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    data.case_id,
    `statement-recovery:${data.source_document_id}`,
    {
      revision: data.recovery_revision,
      sections: [
        makeSection("section-1"),
        { ...makeSection("section-2"), account_number: "", currency: "" },
      ],
      assignments: Object.fromEntries(
        [
          ...data.transactions.map((row) => row.key),
          ...data.incomplete_records.map((row) => row.id),
        ].map((id) => [id, "section-1"])
      ),
      reason: "",
    }
  )
  const [page, setPage] = useState(data.pages[0] || 1)
  const [selected, setSelected] = useState<string[]>([])
  const [target, setTarget] = useState("section-2")
  const [search, setSearch] = useState("")
  const [preview, setPreview] = useState<z.infer<typeof previewSchema> | null>(
    null
  )
  const previewElement = useRef<HTMLElement>(null)
  useEffect(() => {
    if (preview) {
      previewElement.current?.focus()
      previewElement.current?.scrollIntoView({ block: "nearest" })
    }
  }, [preview])
  const [receipt, setReceipt] = useState<z.infer<typeof receiptSchema> | null>(
    null
  )
  const [inspect, setInspect] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const client = useQueryClient()
  const stale = draft.revision !== data.recovery_revision
  const change = (next: typeof draft) => {
    setDraft(next)
    setPreview(null)
    setError("")
  }
  const update = (key: string, patch: Partial<Section>) =>
    change({
      ...draft,
      sections: draft.sections.map((s) =>
        s.key === key ? { ...s, ...patch } : s
      ),
    })
  const balance = (text: string, currency: string, page: number) => {
    if (!text.trim()) return { amount_minor: null, page: null }
    const amount = correctionMinor(text.trim().replace(/^-/, ""), currency)
    if (amount === null)
      throw Error(`Enter a valid balance in ${currency}, or leave it unknown.`)
    return {
      amount_minor: String(
        BigInt(amount) * (text.trim().startsWith("-") ? -1n : 1n)
      ),
      page,
    }
  }
  const submit = async (save: boolean) => {
    setBusy(true)
    setError("")
    try {
      const body = {
        expected_revision: draft.revision,
        reason: draft.reason,
        expected_preview: save ? preview?.revision : null,
        sections: draft.sections.map((s) => ({
          key: s.key,
          holder: s.holder,
          account_number: s.account_number,
          institution: s.institution,
          currency: s.currency,
          period_start: s.period_start,
          period_end: s.period_end,
          transaction_ids: data.transactions
            .filter((r) => draft.assignments[r.key] === s.key)
            .map((r) => r.key),
          incomplete_ids: data.incomplete_records
            .filter((r) => draft.assignments[r.id] === s.key)
            .map((r) => r.id),
          opening: balance(s.opening, s.currency, s.openingPage),
          closing: balance(s.closing, s.currency, s.closingPage),
        })),
      }
      const result = await fetchAPI(
        `/api/financial/statement-import/sources/${data.source_document_id}/recovery/${save ? "save" : "preview"}?case_id=${data.case_id}`,
        { method: "POST", body }
      )
      if (save) {
        const saved = receiptSchema.parse(result)
        if (saved.source_document_id !== data.source_document_id)
          throw Error("The save receipt belongs to a different statement.")
        setReceipt(saved)
        clearDraft()
        await client.invalidateQueries({
          predicate: (query) =>
            query.queryKey.includes(data.case_id) &&
            query.queryKey[0] !== "saved-statement-recovery",
        })
      } else setPreview(previewSchema.parse(result))
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const label = (s: Section) =>
    `${s.holder || "Holder missing"} · ${s.account_number || "Account missing"} · ${s.currency || "Currency missing"}`
  const visible = data.transactions.filter((r) =>
    `${r.description} ${r.ordering_date}`
      .toLowerCase()
      .includes(search.toLowerCase())
  )
  if (receipt)
    return (
      <div className="overflow-y-auto space-y-4 p-1">
        <p role="status">
          Saved {receipt.sections.length} sections. Each payment is counted once
          in its assigned account and currency. Original readings and earlier
          corrections remain in history.
        </p>
        {receipt.sections.map((s) => (
          <div key={s.key} className="border rounded p-3 space-y-2">
            <p>
              {s.currency} · {s.transaction_count} saved payments
            </p>
            <Button
              variant="outline"
              onClick={() =>
                setInspect(
                  inspect === s.source_document_id ? null : s.source_document_id
                )
              }
            >
              Review saved section {s.key.replace("section-", "")}
            </Button>
            {inspect === s.source_document_id && (
              <>
                <ImportedStatementDetails
                  caseId={data.case_id}
                  sourceId={s.source_document_id}
                  initiallyOpen
                />
                <LedgerPanel
                  caseId={data.case_id}
                  params={{ sourceDocumentId: s.source_document_id }}
                  splitAmounts
                />
              </>
            )}
          </div>
        ))}
        <Button onClick={onClose}>Return to statement review</Button>
      </div>
    )
  return (
    <>
      <div className="overflow-y-auto min-h-0 space-y-4 p-1">
        {stale && (
          <div role="alert" className="space-y-2">
            <p>
              The saved import changed while this draft was open. Compare the
              current records before saving. Existing assignments are retained
              where their records still exist; replacement or new records will
              start in Section 1 for review.
            </p>
            <Button
              variant="outline"
              onClick={() =>
                change({
                  ...draft,
                  revision: data.recovery_revision,
                  assignments: Object.fromEntries(
                    [
                      ...data.transactions.map((r) => r.key),
                      ...data.incomplete_records.map((r) => r.id),
                    ].map((id) => [
                      id,
                      draft.assignments[id] || draft.sections[0].key,
                    ])
                  ),
                })
              }
            >
              Use current records and review assignments
            </Button>
          </div>
        )}
        <p className="text-sm">
          Currency changes keep printed numbers unchanged; they do not exchange
          money. Enter balances for each section from its own printed totals, or
          leave them unknown.
        </p>
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label>
              Original PDF page{" "}
              <select
                aria-label="Original PDF page"
                value={page}
                onChange={(e) => setPage(Number(e.target.value))}
              >
                {data.pages.map((p) => (
                  <option key={p} value={p}>
                    {p}
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
          <div className="space-y-3">
            {draft.sections.map((s, index) => (
              <fieldset key={s.key} className="border rounded p-3 space-y-2">
                <legend className="font-medium">Section {index + 1}</legend>
                <div className="grid sm:grid-cols-2 gap-2">
                  {(
                    [
                      ["holder", "Account holder"],
                      ["account_number", "Account number"],
                      ["institution", "Bank"],
                      ["period_start", "Period start"],
                      ["period_end", "Period end"],
                    ] as const
                  ).map(([field, title]) => (
                    <label key={field} className="text-sm">
                      {title}
                      <input
                        className="w-full border rounded p-2"
                        aria-label={`Section ${index + 1} ${title}`}
                        value={s[field]}
                        type={field.startsWith("period") ? "date" : "text"}
                        onChange={(e) =>
                          update(s.key, { [field]: e.target.value })
                        }
                      />
                    </label>
                  ))}
                  <label className="text-sm">
                    Currency
                    <select
                      className="w-full border rounded p-2"
                      aria-label={`Section ${index + 1} Currency`}
                      value={s.currency}
                      onChange={(e) =>
                        update(s.key, { currency: e.target.value })
                      }
                    >
                      <option value="">Choose printed currency</option>
                      <CurrencyOptions />
                    </select>
                  </label>
                  {(["opening", "closing"] as const).map((role) => (
                    <div key={role}>
                      <label className="text-sm">
                        {role} balance
                        <input
                          className="w-full border rounded p-2"
                          aria-label={`Section ${index + 1} ${role} balance`}
                          value={s[role]}
                          placeholder="Unknown"
                          onChange={(e) =>
                            update(s.key, { [role]: e.target.value })
                          }
                        />
                      </label>
                      <label className="text-sm">
                        Source page{" "}
                        <select
                          aria-label={`Section ${index + 1} ${role} balance page`}
                          value={s[`${role}Page`]}
                          onChange={(e) =>
                            update(s.key, {
                              [`${role}Page`]: Number(e.target.value),
                            })
                          }
                        >
                          {data.pages.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  ))}
                </div>
                <p className="text-sm">
                  {
                    Object.values(draft.assignments).filter(
                      (key) => key === s.key
                    ).length
                  }{" "}
                  records assigned
                </p>
                {draft.sections.length > 2 &&
                  !Object.values(draft.assignments).includes(s.key) && (
                    <Button
                      variant="outline"
                      onClick={() => {
                        change({
                          ...draft,
                          sections: draft.sections.filter(
                            (section) => section.key !== s.key
                          ),
                        })
                        if (target === s.key)
                          setTarget(
                            draft.sections.find(
                              (section) => section.key !== s.key
                            )!.key
                          )
                      }}
                    >
                      Remove empty section {index + 1}
                    </Button>
                  )}
              </fieldset>
            ))}
            <Button
              variant="outline"
              disabled={draft.sections.length >= 100}
              onClick={() =>
                change({
                  ...draft,
                  sections: [
                    ...draft.sections,
                    {
                      ...makeSection(
                        `section-${Math.max(...draft.sections.map((s) => Number(s.key.replace("section-", "")))) + 1}`
                      ),
                      account_number: "",
                      currency: "",
                    },
                  ],
                })
              }
            >
              Add another printed section
            </Button>
          </div>
        </div>
        <section aria-label="Assign saved payments" className="space-y-3">
          <h3 className="font-semibold">Assign the saved payments</h3>
          <div className="flex flex-wrap items-end gap-2">
            <label>
              Search saved payments
              <input
                aria-label="Search saved payments"
                className="block border rounded p-2"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <Button
              variant="outline"
              onClick={() => setSelected(visible.map((r) => r.key))}
            >
              Select all {visible.length} matching payments
            </Button>
            <label>
              Destination section
              <select
                aria-label="Destination section"
                className="block border rounded p-2 max-w-full"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {draft.sections.map((s, i) => (
                  <option key={s.key} value={s.key}>
                    {i + 1}: {label(s)}
                  </option>
                ))}
              </select>
            </label>
            <Button
              disabled={!selected.length}
              onClick={() => {
                change({
                  ...draft,
                  assignments: {
                    ...draft.assignments,
                    ...Object.fromEntries(selected.map((id) => [id, target])),
                  },
                })
                setSelected([])
              }}
            >
              Assign {selected.length} selected
            </Button>
          </div>
          <div className="max-h-[350px] overflow-auto border rounded">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th>Select</th>
                  <th>Date / description</th>
                  <th>Amount</th>
                  <th>Section</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={r.key} className="border-t">
                    <td className="p-2">
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.description}`}
                        checked={selected.includes(r.key)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, r.key]
                              : selected.filter((id) => id !== r.key)
                          )
                        }
                      />
                    </td>
                    <td className="p-2">
                      <p>{r.ordering_date}</p>
                      <button
                        className="text-left underline"
                        onClick={() => r.page && setPage(r.page)}
                      >
                        {r.description}
                      </button>
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      {r.direction === "debit" ? "−" : "+"}
                      {correctionMoney(r.amount_minor, r.currency)}
                    </td>
                    <td className="p-2">
                      <select
                        aria-label={`Section for ${r.description}`}
                        value={draft.assignments[r.key]}
                        onChange={(e) =>
                          change({
                            ...draft,
                            assignments: {
                              ...draft.assignments,
                              [r.key]: e.target.value,
                            },
                          })
                        }
                      >
                        {draft.sections.map((s, i) => (
                          <option key={s.key} value={s.key}>
                            Section {i + 1}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.incomplete_records.map((r) => (
            <label key={r.id} className="block">
              Incomplete: {r.fields.description || r.id}
              <select
                aria-label={`Section for incomplete record ${r.id}`}
                value={draft.assignments[r.id]}
                onChange={(e) =>
                  change({
                    ...draft,
                    assignments: {
                      ...draft.assignments,
                      [r.id]: e.target.value,
                    },
                  })
                }
              >
                {draft.sections.map((s, i) => (
                  <option key={s.key} value={s.key}>
                    Section {i + 1}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </section>
        <label className="block">
          Reason for separating these records
          <textarea
            className="block w-full border rounded p-2"
            aria-label="Reason for separating these records"
            value={draft.reason}
            onChange={(e) => change({ ...draft, reason: e.target.value })}
          />
        </label>
        {preview && (
          <section
            ref={previewElement}
            tabIndex={-1}
            aria-label="Review section changes"
            className="border rounded p-3 space-y-2"
          >
            <h3 className="font-semibold">Review before saving</h3>
            <p>{preview.explanation}</p>
            {preview.sections.map((s) => (
              <p key={s.key}>
                {s.holder} · {s.account_number} · {s.currency}:{" "}
                {s.transaction_count} payments, {s.incomplete_count} incomplete
                records. In {correctionMoney(s.credit_minor, s.currency)}; out{" "}
                {correctionMoney(s.debit_minor, s.currency)}.
              </p>
            ))}
          </section>
        )}
      </div>
      <div className="border-t pt-3 space-y-2">
        {error && (
          <div role="alert" className="space-y-2">
            <p className="text-destructive">{error}</p>
            <Button variant="outline" disabled={busy} onClick={onReload}>
              Reload current records; keep assignments
            </Button>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Close and keep draft
          </Button>
          <Button disabled={busy || stale} onClick={() => void submit(false)}>
            {busy ? "Checking…" : "Review section assignments"}
          </Button>
          {preview && (
            <Button disabled={busy || stale} onClick={() => void submit(true)}>
              Save {preview.sections.length} separate sections
            </Button>
          )}
        </div>
      </div>
    </>
  )
}
