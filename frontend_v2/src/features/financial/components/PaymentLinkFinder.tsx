import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
import { agentAPI } from "@/features/agent/api"
import { savedTrail, trailPreview } from "../lib/money-trails"
import {
  citedPaymentIds,
  LEVEL_WORDS,
  linkSuggestionAPI,
  type LinkPayment,
  type LinkSuggestion,
  type LinkSuggestions,
} from "../lib/link-suggestions"
import { Disclosure } from "./Disclosure"

const LEVEL_CLASS: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
  moderate: "bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100",
  weak: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  faint: "bg-muted text-muted-foreground",
}

/** Where a suggestion came from, for the link record and the label beside it. */
type Origin =
  | { kind: "rule"; rule: string }
  | { kind: "model"; model: string; provider: string; runId: string; at: string }

export type UseInForm = {
  debit: string
  credit: string
  split?: boolean
  fx?: boolean
}

function LevelBadge({ level }: { level: string | null }) {
  if (!level) return null
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-semibold ${LEVEL_CLASS[level] || ""}`}
    >
      {LEVEL_WORDS[level] || level}
    </span>
  )
}

export function PaymentRow({
  p,
  children,
}: {
  p: LinkPayment & { level?: string | null; reasons?: string }
  children?: React.ReactNode
}) {
  return (
    <li
      className="rounded border p-2 text-sm"
      aria-label={`${p.ref_id} ${p.amount} ${p.date || ""}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {"level" in p && <LevelBadge level={p.level ?? null} />}
        <span className="font-medium">{p.date || "no date"}</span>
        <span className="font-medium tabular-nums">{p.amount}</span>
        <span>
          {p.direction === "debit" ? "Money out" : "Money in"} · From{" "}
          <b>{p.from_name}</b> to <b>{p.to_name}</b>
        </span>
      </div>
      <div className="text-muted-foreground">
        {p.account_label} · {p.ref_id}
        {p.description ? ` · ${p.description.slice(0, 140)}` : ""}
      </div>
      {p.reasons && <p>{p.reasons}</p>}
      {children && <div className="mt-1 flex flex-wrap gap-2">{children}</div>}
    </li>
  )
}

function Paged({
  data,
  page,
  setPage,
  label,
}: {
  data: LinkSuggestions
  page: number
  setPage: (n: number) => void
  label: string
}) {
  if (data.pages <= 1) return null
  const first = (data.page - 1) * data.page_size + 1
  const last = first + data.candidates.length - 1
  return (
    <nav aria-label={label} className="flex items-center gap-2 text-sm">
      Showing {first}–{last} of {data.total}
      <Button
        variant="outline"
        size="sm"
        disabled={page <= 1}
        onClick={() => setPage(page - 1)}
      >
        Previous
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= data.pages}
        onClick={() => setPage(page + 1)}
      >
        Next
      </Button>
    </nav>
  )
}

function Counts({ data }: { data: LinkSuggestions }) {
  const parts = ["strong", "moderate", "weak", "faint"]
    .filter((l) => data.by_level[l])
    .map((l) => `${data.by_level[l]} ${l}`)
  return (
    <p className="text-sm">
      {data.total === 0
        ? "No payment in this case meets a connecting rule."
        : `${data.total} suggested (${parts.join(", ")}), strongest first.`}{" "}
      <span className="text-muted-foreground">
        Compared {data.compared} payment{data.compared === 1 ? "" : "s"} in{" "}
        {(data.elapsed_ms / 1000).toFixed(1)} s.
      </span>
    </p>
  )
}

/**
 * Suggested connected payments for one payment, a case-wide search and a question to the case agent, in one list
 * format. A person links a suggestion with one click; nothing is ever linked automatically.
 */
export function PaymentLinkFinder({
  caseId,
  anchorId,
  canLink,
  onOpen,
  onUseInForm,
}: {
  caseId: string
  anchorId: string
  canLink: boolean
  onOpen?: (id: string) => void
  onUseInForm?: (value: UseInForm) => void
}) {
  const client = useQueryClient()
  // the trail being walked: the anchor first, then each payment followed
  const [path, setPath] = useState<LinkPayment[]>([])
  const [mode, setMode] = useState<"connected" | "onward">("connected")
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState("")
  const [searched, setSearched] = useState("")
  const [searchPage, setSearchPage] = useState(1)
  const [question, setQuestion] = useState("")
  const [linked, setLinked] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<{
    candidate: LinkSuggestion
    message: string
  } | null>(null)
  const focus = path[path.length - 1]
  const focusId = focus?.id || anchorId
  const suggestions = useQuery({
    queryKey: ["financial-ledger", caseId, "link-suggestions", focusId, mode, page],
    queryFn: () => linkSuggestionAPI.suggestions(caseId, focusId, mode, page),
    retry: false,
  })
  const anchor = suggestions.data?.anchor ?? focus
  const search = useQuery({
    queryKey: ["financial-ledger", caseId, "link-search", focusId, searched, searchPage],
    queryFn: () =>
      linkSuggestionAPI.search(caseId, searched, {
        transactionId: focusId,
        page: searchPage,
      }),
    enabled: !!searched,
    retry: false,
  })
  const ask = useMutation({
    mutationFn: async () => {
      if (!anchor) throw Error("The payment is still loading.")
      const asked = new Date()
      const answer = await agentAPI.sendMessage({
        caseId,
        message:
          `About payment ${anchor.ref_id} (id ${anchor.id}): ${anchor.amount}, ${anchor.direction === "debit" ? "money out" : "money in"} on ${anchor.date || "no printed date"}, ` +
          `account ${anchor.account_label}, from ${anchor.from_name} to ${anchor.to_name}. ` +
          `${question.trim()}\n\nUse find_connected_payments for this payment (mode connected, onward or search) and cite each payment you name with its link. ` +
          `Do not link anything: list candidates for a person to check.`,
      })
      const ids = citedPaymentIds(answer.answer)
      const named = ids.length
        ? await linkSuggestionAPI.named(caseId, anchor.id, ids)
        : null
      return { answer, named, asked }
    },
    retry: false,
  })
  const link = useMutation({
    mutationFn: async ({
      candidate,
      origin,
      onward,
    }: {
      candidate: LinkSuggestion
      origin: Origin
      onward: boolean
    }) => {
      if (!anchor) throw Error("The payment is still loading.")
      const by =
        origin.kind === "rule"
          ? `Suggested by the ${origin.rule === "onward_payment" ? "onward-payment" : "connected-payment"} rule (${candidate.level || "search"}): ${candidate.reasons}`
          : `Suggested by the case agent (model ${origin.model}, ${origin.provider}, run ${origin.runId}, ${origin.at}); linked by the person saving it`
      const minor = (a: string, b: string) =>
        BigInt(a) < BigInt(b) ? a : b
      const body = onward
        ? {
            id: randomRequestId(),
            expected_revision: 0,
            kind: "allocation",
            credit_id: anchor.id,
            payments: [
              {
                transaction_id: candidate.id,
                amount_minor: minor(candidate.amount_minor, anchor.amount_minor),
              },
            ],
            reason: `Onward payment linked from a suggestion: ${candidate.reasons}`,
            suggested_by: by,
          }
        : {
            id: randomRequestId(),
            expected_revision: 0,
            kind: "transfer",
            debit_id: anchor.direction === "debit" ? anchor.id : candidate.id,
            credit_id: anchor.direction === "credit" ? anchor.id : candidate.id,
            allow_fx: candidate.currency !== anchor.currency,
            reason: `Linked from a suggestion: ${candidate.reasons}`,
            suggested_by: by,
          }
      const qs = new URLSearchParams({ case_id: caseId })
      const preview = trailPreview.parse(
        await fetchAPI(`/api/financial/money-trails/preview?${qs}`, {
          method: "POST",
          body,
        })
      )
      const saved = savedTrail.parse(
        await fetchAPI(`/api/financial/money-trails?${qs}`, {
          method: "POST",
          body: { ...body, expected_source_revision: preview.source_revision },
        })
      )
      if (saved.case_id !== caseId)
        throw Error("The saved link could not be confirmed.")
      return { candidate, saved }
    },
    onMutate: () => setFailed(null),
    onSuccess: async ({ candidate }) => {
      setLinked((l) => ({ ...l, [candidate.id]: "Linked and saved to this case." }))
      await client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
    onError: (error, { candidate }) =>
      setFailed({
        candidate,
        message: error instanceof Error ? error.message : String(error),
      }),
    retry: false,
  })
  const follow = (p: LinkPayment) => {
    setPath((x) => [...x, p])
    setMode(p.direction === "credit" ? "onward" : "connected")
    setPage(1)
    setSearched("")
  }
  const back = () => {
    setPath((x) => x.slice(0, -1))
    const previous = path[path.length - 2]
    setMode(previous && previous.direction === "credit" ? "onward" : "connected")
    setPage(1)
    setSearched("")
  }
  const actions = (c: LinkSuggestion, origin: Origin) => {
    // money out of the account this receipt arrived in is an onward allocation, not the receipt's other side
    const onward =
      anchor?.direction === "credit" &&
      c.direction === "debit" &&
      (mode === "onward" || c.account_id === anchor.account_id)
    return (
    <>
      {canLink &&
        (linked[c.id] ? (
          <span role="status">{linked[c.id]}</span>
        ) : (
          <Button
            size="sm"
            disabled={link.isPending}
            onClick={() => link.mutate({ candidate: c, origin, onward })}
          >
            {onward ? "Link as onward payment" : "Link"}
          </Button>
        ))}
      <Button size="sm" variant="outline" onClick={() => follow(c)}>
        Follow this payment
      </Button>
      {onOpen && (
        <Button size="sm" variant="outline" onClick={() => onOpen(c.id)}>
          Open source
        </Button>
      )}
    </>
    )
  }
  const list = (data: LinkSuggestions, label: string, origin: Origin) => (
    <ol aria-label={label} className="space-y-2">
      {data.candidates.map((c) => (
        <PaymentRow key={c.id} p={c}>
          {actions(c, origin)}
          {failed?.candidate.id === c.id && (
            <div role="alert" className="basis-full">
              {failed.message}
              {onUseInForm && anchor && (
                <Button
                  size="sm"
                  variant="link"
                  onClick={() =>
                    onUseInForm({
                      debit: anchor.direction === "debit" ? anchor.id : c.id,
                      credit: anchor.direction === "credit" ? anchor.id : c.id,
                      split:
                        c.currency === anchor.currency &&
                        c.amount_minor !== anchor.amount_minor,
                      fx: c.currency !== anchor.currency,
                    })
                  }
                >
                  Open in the link form (fees, splits or part payments)
                </Button>
              )}
            </div>
          )}
        </PaymentRow>
      ))}
    </ol>
  )
  return (
    <section
      aria-label="Suggested connected payments"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">
        {path.length ? "Following the money" : "Suggested connected payments"}
      </h3>
      {path.length > 0 && (
        <nav aria-label="Trail" className="flex flex-wrap items-center gap-2 text-sm">
          <Button size="sm" variant="outline" onClick={back}>
            Back
          </Button>
          <span>
            Step {path.length}: {focus.date} · {focus.amount} · {focus.account_label}
          </span>
        </nav>
      )}
      {anchor && (
        <ul className="list-none">
          <PaymentRow p={anchor} />
        </ul>
      )}
      <div role="tablist" className="flex flex-wrap gap-2">
        <Button
          role="tab"
          aria-selected={mode === "connected"}
          size="sm"
          variant={mode === "connected" ? "primary" : "outline"}
          onClick={() => {
            setMode("connected")
            setPage(1)
          }}
        >
          {anchor?.direction === "credit"
            ? "Where it came from"
            : "Where it arrived (other side)"}
        </Button>
        {anchor?.direction === "credit" && (
          <Button
            role="tab"
            aria-selected={mode === "onward"}
            size="sm"
            variant={mode === "onward" ? "primary" : "outline"}
            onClick={() => {
              setMode("onward")
              setPage(1)
            }}
          >
            Where it went next
          </Button>
        )}
      </div>
      {suggestions.isPending && (
        <p role="status">
          Looking across every payment in this case for{" "}
          {mode === "onward"
            ? "payments out of the receiving account after this one"
            : "its other side: matching amounts, dates, references, account numbers and names"}
          …
        </p>
      )}
      {suggestions.isError && (
        <p role="alert">
          {suggestions.error instanceof Error
            ? suggestions.error.message
            : "Suggestions could not be loaded."}
        </p>
      )}
      {suggestions.data && (
        <>
          <Counts data={suggestions.data} />
          {suggestions.data.left_out?.words && (
            <p className="text-sm">{suggestions.data.left_out.words}</p>
          )}
          {suggestions.data.left_out?.common_words && (
            <p className="text-sm text-muted-foreground">
              {suggestions.data.left_out.common_words}
            </p>
          )}
          {list(
            suggestions.data,
            mode === "onward" ? "Onward payments" : "Suggested other sides",
            {
              kind: "rule",
              rule: mode === "onward" ? "onward_payment" : "connected_payment",
            }
          )}
          <Paged
            data={suggestions.data}
            page={page}
            setPage={setPage}
            label="Suggestion pages"
          />
          <Disclosure label="How strength is set">
            <p className="text-sm">{suggestions.data.rule}</p>
          </Disclosure>
        </>
      )}
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault()
          setSearched(query.trim())
          setSearchPage(1)
        }}
      >
        <label className="block">
          Search this case
          <input
            className="block w-full rounded border bg-background p-2"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name, reference, account number, amount (825.62, 800-900, 825±10) or dates (2024-01-02..2024-01-09)"
          />
        </label>
        <Button type="submit" size="sm" disabled={!query.trim()}>
          Search
        </Button>
      </form>
      {search.isFetching && <p role="status">Searching every payment in this case…</p>}
      {search.isError && (
        <p role="alert">
          {search.error instanceof Error ? search.error.message : "Search failed."}
        </p>
      )}
      {search.data && searched && (
        <>
          <p className="text-sm">
            {search.data.total} found
            {search.data.understood ? ` (${search.data.understood})` : ""},
            graded against this payment.
          </p>
          {list(search.data, "Search results", { kind: "rule", rule: "search" })}
          <Paged
            data={search.data}
            page={searchPage}
            setPage={setSearchPage}
            label="Search result pages"
          />
        </>
      )}
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (question.trim()) ask.mutate()
        }}
      >
        <label className="block">
          Ask the case agent
          <input
            className="block w-full rounded border bg-background p-2"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Where did this money go next? Find the payment that funded this."
          />
        </label>
        <Button type="submit" size="sm" disabled={!question.trim() || ask.isPending}>
          Ask
        </Button>
      </form>
      {ask.isPending && (
        <p role="status">The case agent is reading this case's payments…</p>
      )}
      {ask.isError && (
        <p role="alert">
          {ask.error instanceof Error ? ask.error.message : "The question could not be answered."}
        </p>
      )}
      {ask.data && (
        <section aria-label="Model suggestion" className="space-y-2 rounded border border-dashed p-2">
          <p className="text-sm font-semibold">
            Model suggestion · {ask.data.answer.model_info.model_name} (
            {ask.data.answer.model_info.provider}) · asked{" "}
            {ask.data.asked.toLocaleString()} · not linked: a person checks and
            links
          </p>
          <p className="whitespace-pre-wrap text-sm">{ask.data.answer.answer}</p>
          {ask.data.named && ask.data.named.candidates.length > 0 &&
            list(ask.data.named, "Payments the model suggests", {
              kind: "model",
              model: ask.data.answer.model_info.model_name,
              provider: ask.data.answer.model_info.provider,
              runId: ask.data.answer.run_id,
              at: ask.data.asked.toISOString(),
            })}
          {ask.data.named && ask.data.named.not_found ? (
            <p className="text-sm">
              {ask.data.named.not_found} cited payment
              {ask.data.named.not_found === 1 ? " is" : "s are"} not a current
              payment of this case and {ask.data.named.not_found === 1 ? "is" : "are"} not shown.
            </p>
          ) : null}
        </section>
      )}
    </section>
  )
}

/** Choose one payment for a role in the link form by searching the case (no list of every payment). */
export function PaymentPicker({
  caseId,
  direction,
  anchorId,
  label,
  onPick,
}: {
  caseId: string
  direction: "debit" | "credit"
  anchorId?: string
  label: string
  onPick: (p: LinkSuggestion) => void
}) {
  const [query, setQuery] = useState("")
  const [searched, setSearched] = useState("")
  const [page, setPage] = useState(1)
  const result = useQuery({
    queryKey: ["financial-ledger", caseId, "link-pick", direction, anchorId, searched, page],
    queryFn: () =>
      linkSuggestionAPI.search(caseId, searched, {
        transactionId: anchorId,
        direction,
        page,
      }),
    enabled: !!searched,
    retry: false,
  })
  return (
    <div className="space-y-2">
      <label className="block">
        {label}
        <span className="flex gap-2">
          <input
            className="block w-full rounded border bg-background p-2"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                setSearched(query.trim())
                setPage(1)
              }
            }}
            placeholder="Name, reference, account number, amount or dates"
          />
          <Button
            type="button"
            size="sm"
            disabled={!query.trim()}
            onClick={() => {
              setSearched(query.trim())
              setPage(1)
            }}
          >
            Search
          </Button>
        </span>
      </label>
      {result.isFetching && <p role="status">Searching every payment in this case…</p>}
      {result.isError && (
        <p role="alert">
          {result.error instanceof Error ? result.error.message : "Search failed."}
        </p>
      )}
      {result.data && searched && (
        <>
          <p className="text-sm">
            {result.data.total} found
            {result.data.understood ? ` (${result.data.understood})` : ""}.
          </p>
          <ol className="max-h-72 space-y-2 overflow-auto">
            {result.data.candidates.map((c) => (
              <PaymentRow key={c.id} p={c}>
                <Button size="sm" variant="outline" onClick={() => onPick(c)}>
                  Choose
                </Button>
              </PaymentRow>
            ))}
          </ol>
          <Paged data={result.data} page={page} setPage={setPage} label={`${label} pages`} />
        </>
      )}
    </div>
  )
}
