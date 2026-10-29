import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import type { LedgerTransaction } from "../api"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { usePaymentCategoryLibrary } from "../hooks/use-payment-category-library"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { categoryTone } from "../lib/category-palette"
import { formatLedgerAmount } from "../lib/ledger-format"
import { InfoTip } from "./InfoTip"

const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.025em" }
const eyebrow = "font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground"
const ORIGIN: Record<string, string> = {
  description: "Loupe's rule",
  model: "Loupe's model guess",
  learned: "Learned from a person's choice",
  investigator: "A person chose this",
  statement: "Printed on the statement",
  account: "From the account",
}
type Like = {
  case_id: string
  count: number
  basis?: string
  transaction_ids: string[]
  first_date?: string | null
  last_date?: string | null
  examples?: { id: string; date: string; description: string }[]
}
const day = (value?: string | null) =>
  value
    ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      })
    : ""
const errorText = (error: Error) =>
  error instanceof ApiError && (/^[{[]/.test(error.message) || error.message.length > 500)
    ? "The category could not be saved. Reload the selection and try again."
    : error.message

/**
 * Categorise one payment (or several selected): Loupe's current suggestion
 * first, every category as a coloured tile, "apply to the N like this", and
 * Save · next to walk the current list. The full field editor (with its
 * review step) stays one click away.
 */
export function CategorisePaymentDialog({
  caseId,
  ids,
  progress,
  onNext,
  onSkip,
  onMoreFields,
  onManage,
  onSaved,
  onClose,
}: {
  caseId: string
  ids: string[]
  /** Saved so far / payments in the current list, when walking a list. */
  progress?: { done: number; total: number }
  onNext?: () => void
  onSkip?: () => void
  onMoreFields: () => void
  onManage?: () => void
  onSaved: (replacements: { previous_id: string; id: string }[]) => void
  onClose: () => void
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const library = usePaymentCategoryLibrary(caseId)
  const [choice, setChoice] = useState<string | null>(null)
  const [typed, setTyped] = useState("")
  const [creating, setCreating] = useState(false)
  const [applyLike, setApplyLike] = useState(true)
  const [makeRule, setMakeRule] = useState(false)
  const [andNext, setAndNext] = useState(false)
  const single = ids.length === 1
  const query = useQuery({
    queryKey: ["payment-edit-selection", caseId, ids],
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: async () => {
      const rows: LedgerTransaction[] = []
      for (let offset = 0; offset < ids.length; offset += 500)
        rows.push(...(await readSelectedPayments(caseId, ids.slice(offset, offset + 500))).map((source) => source.transaction))
      if (rows.length !== ids.length || new Set(rows.map((row) => row.key)).size !== ids.length || rows.some((row) => !ids.includes(row.key)))
        throw Error("The complete selection could not be loaded. Reload before saving.")
      return rows
    },
  })
  const like = useQuery({
    queryKey: ["payment-category-like", caseId, ids[0]],
    enabled: single && canEdit,
    retry: false,
    queryFn: async () => {
      const result = await fetchAPI<Like>(
        `/api/financial/ledger/payment-categories/like?${new URLSearchParams({ case_id: caseId, transaction_id: ids[0] })}`
      )
      if (result.case_id !== caseId) throw Error("Similar payments came from a different case.")
      return result
    },
  })
  const row = single ? query.data?.[0] : undefined
  const origin = row?.label_sources?.category
  const current = [...new Set(query.data?.map((item) => item.category || "Uncategorized"))]
  const suggestion =
    row && row.category && row.category !== "Uncategorized" && origin && origin.source !== "investigator" ? row.category : null
  const names = [
    ...new Set([...(library.data ?? []).map((item) => item.name), ...current.filter((name) => name !== "Uncategorized")]),
  ].sort((a, b) => a.localeCompare(b))
  const colors = new Map((library.data ?? []).map((item) => [item.name.toLowerCase(), item.color]))
  const tiles = [...(suggestion ? [suggestion] : []), ...names.filter((name) => name !== suggestion), "Uncategorized"]
  const picked = choice ?? suggestion
  const chosen = creating ? typed.trim() : picked
  const isNew = !!chosen && creating && !names.some((name) => name.toLowerCase() === chosen.toLowerCase()) && chosen.toLowerCase() !== "uncategorized"
  const likeCount = like.data?.count ?? 0
  const save = useMutation({
    mutationFn: async (category: string) => {
      if (!query.data) throw Error("The selection is still loading.")
      const body = {
        transactions: query.data.map((item) => ({ id: item.key, version: item.label_version ?? 0 })),
        changes: { category },
      }
      const preview = await fetchAPI<{ case_id: string; revision: string; count: number }>(
        `/api/financial/ledger/payment-edits/preview?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body }
      )
      if (preview.case_id !== caseId || preview.count !== ids.length || !/^[a-f0-9]{64}$/.test(preview.revision))
        throw Error("The preview did not match this selection. Reload before saving.")
      const result = await fetchAPI<{ case_id: string; updated: number; replacements: { previous_id: string; id: string }[] }>(
        `/api/financial/ledger/payment-edits/confirm?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body: { ...body, expected_revision: preview.revision } }
      )
      if (
        result.case_id !== caseId ||
        result.updated !== ids.length ||
        result.replacements.length !== ids.length ||
        result.replacements.some((item) => !ids.includes(item.previous_id))
      )
        throw Error("The complete save was not confirmed. Reload the selection before trying again.")
      let learned = 0
      if (single && applyLike && like.data?.count) {
        try {
          const applied = await fetchAPI<{ case_id: string; updated: number }>(
            `/api/financial/ledger/payment-categories/apply-like?${new URLSearchParams({ case_id: caseId })}`,
            {
              method: "POST",
              body: { transaction_id: result.replacements[0].id, category, transaction_ids: like.data.transaction_ids },
            }
          )
          learned = applied.updated
        } catch {
          toast.error("The category was saved, but could not be applied to the similar payments.")
        }
      }
      let ruled = false
      if (single && makeRule) {
        try {
          await fetchAPI(
            `/api/financial/ledger/payment-categories/rules?${new URLSearchParams({ case_id: caseId })}`,
            { method: "POST", body: { transaction_id: result.replacements[0].id, category } }
          )
          ruled = true
        } catch (error) {
          toast.error(
            `The category was saved, but the rule for future statements was not: ${error instanceof Error ? error.message : "try again"}.`
          )
        }
      }
      return { result, learned, category, ruled }
    },
    onSuccess: async ({ result, learned, category, ruled }) => {
      await client.invalidateQueries({
        predicate: (item) =>
          /financial|ledger|payment|statement-import/.test(String(item.queryKey[0])) &&
          (item.queryKey.includes(caseId) || item.queryKey[0] === "financial-category-library"),
      })
      onSaved(result.replacements)
      toast.success(
        `${category} saved for ${result.updated + learned} ${result.updated + learned === 1 ? "payment" : "payments"}${learned ? ` (${learned} similar)` : ""}.${ruled ? " Future statements will use it for payments like this." : ""}`
      )
      if (andNext && onNext) onNext()
      else onClose()
    },
  })
  const busy = save.isPending
  const ready = !!query.data && !query.isFetching && !!chosen && !busy && !library.isPending
  const submit = (next: boolean) => {
    if (!ready || !chosen) return
    setAndNext(next)
    save.mutate(chosen)
  }
  // 1–9 picks a tile, Enter saves (and opens the next one when walking a list).
  const keys = useRef({ tiles, submit, creating })
  useEffect(() => {
    keys.current = { tiles, submit, creating }
  })
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
      if (/^[1-9]$/.test(event.key)) {
        const name = keys.current.tiles[Number(event.key) - 1]
        if (name) {
          setCreating(false)
          setChoice(name)
          event.preventDefault()
        }
      } else if (event.key === "Enter" && !(target?.tagName === "BUTTON")) {
        keys.current.submit(!!onNext)
        event.preventDefault()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onNext])
  if (!canEdit) return null
  const amount = row ? formatLedgerAmount(String(row.amount_minor), row.currency).text : ""
  const tile = (name: string, index: number, suggested = false) => {
    const tone = categoryTone(name, colors.get(name.toLowerCase()))
    const selected = !creating && picked === name
    return (
      <button
        key={name}
        type="button"
        aria-pressed={selected}
        disabled={busy}
        onClick={() => {
          setCreating(false)
          setChoice(name)
        }}
        className="flex min-h-11 items-center gap-2.5 rounded-[10px] px-3.5 py-2.5 text-left text-sm font-semibold outline-offset-2 focus-visible:outline-3"
        style={{
          background: tone.tint,
          color: tone.text,
          boxShadow: selected ? `0 0 0 2px ${tone.dot}` : undefined,
          ...(name === "Uncategorized" ? { border: "1.5px dashed #d99a2b" } : {}),
        }}
      >
        {selected ? (
          <span aria-hidden="true" className="inline-flex size-5 items-center justify-center rounded-full text-[12px] text-white" style={{ background: tone.dot }}>
            ✓
          </span>
        ) : (
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full" style={{ background: tone.dot }} />
        )}
        <span className="min-w-0">
          <span className="block">{name}</span>
          {suggested && origin && (
            <span className="block text-[12.5px] font-normal opacity-90">
              {ORIGIN[origin.source] || "Automatic"}
              {origin.explanation ? ` · ${origin.explanation}` : ""}
              {origin.confidence != null ? ` · ${Math.round(origin.confidence * 100)}% sure` : ""}
            </span>
          )}
        </span>
        {index < 9 && (
          <span aria-hidden="true" className="ml-auto pl-2 font-mono text-[11px] opacity-60">
            {index + 1}
          </span>
        )}
      </button>
    )
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl" showCloseButton={!busy}>
        <div className="flex shrink-0 items-start gap-3 bg-[#0b0c0f] p-5 pr-12 text-[#f7f7f8]">
          <div className="min-w-0 flex-1">
            <DialogTitle className="text-lg font-semibold" style={heading}>
              {single ? row?.account_label || "Categorise a payment" : `Categorise ${ids.length.toLocaleString()} selected payments`}
            </DialogTitle>
            <DialogDescription className="mt-0.5 text-[13px] text-[#bfc1c8]">
              {single
                ? row
                  ? [day(row.ordering_date), row.description || row.ref_id].filter(Boolean).join(" · ")
                  : "Loading the payment…"
                : "Applies to every selected payment, across pages."}
            </DialogDescription>
          </div>
          {row && (
            <span
              className={`shrink-0 text-2xl font-semibold tabular-nums ${row.direction === "credit" ? "text-[#5fd39a]" : ""}`}
              style={heading}
            >
              <span aria-hidden="true">{row.direction === "credit" ? "↓ +" : "↑ −"}</span>
              <span className="sr-only">{row.direction === "credit" ? "Money in " : "Money out "}</span>
              {amount} <span className="text-sm text-[#9a9da5]">{row.currency}</span>
            </span>
          )}
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {query.isPending && <p role="status">Loading selected payments…</p>}
          {query.data && (
            <p className="text-sm">
              Now: {current.join(", ")}
              <InfoTip text="Your category replaces any current category or automatic suggestion and stays saved when you return. A person's choice is never changed by Loupe. Choose Uncategorized to remove a category. Original statement values remain unchanged." />
            </p>
          )}
          {suggestion && (
            <section aria-label="Loupe suggests" className="space-y-2">
              <span className={eyebrow}>Loupe suggests</span>
              <div className="grid gap-2">{tile(suggestion, 0, true)}</div>
            </section>
          )}
          <section aria-label="Or pick one" className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className={eyebrow}>{suggestion ? "Or pick one" : "Pick a category"}</span>
              {onManage && (
                <button type="button" className="text-sm font-semibold text-[#1d4aa6] hover:underline dark:text-[#9bb8f0]" onClick={onManage}>
                  Manage categories
                </button>
              )}
            </div>
            {library.isPending && <p role="status">Loading categories…</p>}
            {library.isError && (
              <p role="alert">
                The category library could not be loaded.{" "}
                <button className="underline" onClick={() => void library.refetch()}>
                  Reload categories
                </button>
              </p>
            )}
            <div className="grid gap-2 sm:grid-cols-3">
              {tiles.slice(suggestion ? 1 : 0).map((name, index) => tile(name, index + (suggestion ? 1 : 0)))}
              <button
                type="button"
                aria-pressed={creating}
                disabled={busy}
                onClick={() => setCreating(true)}
                className="flex min-h-11 items-center rounded-[10px] border-[1.5px] border-dashed px-3.5 py-2.5 text-sm font-semibold"
              >
                + New category
              </button>
            </div>
            {creating && (
              <label className="block text-sm">
                New category name
                <input
                  autoFocus
                  aria-label="New category name"
                  maxLength={120}
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault()
                      submit(!!onNext)
                    }
                  }}
                  className="mt-1 block w-full rounded-lg border bg-background p-2"
                  placeholder="Type a name"
                />
              </label>
            )}
            {isNew && (
              <p role="status" className="text-sm">
                Saving will create “{chosen}” and apply it to {ids.length} {ids.length === 1 ? "payment" : "payments"}.
              </p>
            )}
          </section>
          {single && like.data && likeCount > 0 && (
            <section aria-label="Payments like this" className="space-y-2 rounded-xl bg-[#e8effd] p-4 text-[#14161b] dark:bg-[#1d2a44] dark:text-[#f7f7f8]">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1 size-4"
                  checked={applyLike}
                  disabled={busy}
                  onChange={(event) => setApplyLike(event.target.checked)}
                />
                <span>
                  <strong className="block">
                    Also apply to the {likeCount.toLocaleString()} other {likeCount === 1 ? "payment" : "payments"} like this
                  </strong>
                  <span className="text-[13px]">
                    {like.data.basis ? `${like.data.basis[0].toUpperCase()}${like.data.basis.slice(1)}` : "Similar"}
                    {like.data.first_date ? ` · ${day(like.data.first_date)} to ${day(like.data.last_date)}` : ""}
                    {" · "}a person's own choices are never changed
                  </span>
                </span>
              </label>
              {!!like.data.examples?.length && (
                <ul className="flex flex-wrap gap-1.5 pl-7" aria-label="Some of them">
                  {like.data.examples.map((item) => (
                    <li key={item.id} className="rounded-md bg-white/70 px-2 py-0.5 text-[12.5px] dark:bg-black/20">
                      {day(item.date)} · {item.description.slice(0, 40) || "No description"}
                    </li>
                  ))}
                  {likeCount > like.data.examples.length && (
                    <li className="px-1 text-[12.5px] font-semibold">+{(likeCount - like.data.examples.length).toLocaleString()} more</li>
                  )}
                </ul>
              )}
            </section>
          )}
          {single && like.isSuccess && (
            <label className="flex items-start gap-3 rounded-xl border p-3 text-sm">
              <input
                type="checkbox"
                className="mt-1 size-4"
                checked={makeRule}
                disabled={busy}
                onChange={(event) => setMakeRule(event.target.checked)}
              />
              <span>
                <strong className="block">Make this a rule for future statements too</strong>
                <span className="text-[13px] text-muted-foreground">
                  Payments {like.data.basis === "same counterparty" ? "with this counterparty" : "described like this"} in
                  statements read later get this category · a person's own choices still win
                </span>
              </span>
            </label>
          )}
          {like.isError && single && (
            <p className="text-[13px] text-muted-foreground">Similar payments could not be checked; this payment can still be saved.</p>
          )}
        </div>
        <div className="shrink-0 space-y-2 border-t bg-background p-4">
          {(save.error || query.error) && (
            <p role="alert" className="max-h-24 overflow-auto text-sm text-destructive">
              {errorText((save.error || query.error)!)}{" "}
              <button
                type="button"
                className="underline"
                disabled={busy}
                onClick={() => {
                  save.reset()
                  void query.refetch()
                }}
              >
                Reload selection
              </button>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-auto text-[12.5px] text-muted-foreground">
              Keys: 1–9 picks, Enter saves{onNext ? " and opens the next" : ""}
            </span>
            <button type="button" disabled={busy} onClick={onMoreFields} className="rounded-lg px-3 py-2 text-sm font-semibold hover:bg-muted">
              Edit other fields…
            </button>
            {onSkip && (
              <button type="button" disabled={busy} onClick={onSkip} className="rounded-lg border px-4 py-2 text-sm font-semibold hover:bg-muted">
                Skip
              </button>
            )}
            {!onSkip && (
              <button type="button" disabled={busy} onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-semibold hover:bg-muted">
                Cancel
              </button>
            )}
            {onNext && (
              <button type="button" disabled={!ready} onClick={() => submit(false)} className="rounded-lg border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50">
                Save
              </button>
            )}
            <button
              type="button"
              disabled={!ready}
              onClick={() => submit(!!onNext)}
              className="rounded-lg bg-[#b41624] px-4 py-2 text-sm font-semibold text-white hover:bg-[#9a121f] disabled:opacity-50"
            >
              {busy
                ? "Saving…"
                : `Save ${(ids.length + (single && applyLike ? likeCount : 0)).toLocaleString()} ${ids.length + (single && applyLike ? likeCount : 0) === 1 ? "payment" : "payments"}${onNext ? " · next →" : ""}`}
            </button>
          </div>
        </div>
        {progress && progress.total > 1 && (
          <div className="shrink-0 bg-[#0b0c0f] px-5 pb-3 pt-2 text-[12.5px] text-[#bfc1c8]">
            <div className="mb-1.5 h-1 overflow-hidden rounded bg-[#292b32]">
              <span className="block h-full bg-[#2fae6c]" style={{ width: `${Math.min(100, (progress.done / progress.total) * 100)}%` }} />
            </div>
            {progress.done.toLocaleString()} of {progress.total.toLocaleString()} done in this view · the "Where it went" tiles update as you save
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
