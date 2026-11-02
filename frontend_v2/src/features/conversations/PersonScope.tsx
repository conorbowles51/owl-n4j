import { useQuery } from "@tanstack/react-query"
import { getLinkedIdentities, getParticipants, streamIndex, type StreamFilter } from "@/features/phones/api"
import type { ConversationView } from "@/features/phones/lib/filter-url"

const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

const MODES: { mode: ConversationView["mode"]; words: string }[] = [
  { mode: "between", words: "Between A and B" },
  { mode: "sent-by", words: "Sent by A" },
  { mode: "sent-to", words: "Sent to A" },
  { mode: "involving", words: "Involving A" },
]

/**
 * The chosen person in the scope bar (07 J-3): who A is and on how many of the case's phones, the four ways of
 * reading A (B is the second person, or with one person the owner of each phone), All channels, and the switch
 * that takes in A's other numbers and accounts, off by default with its effect stated.
 */
export function PersonScope(props: {
  caseId: string
  view: ConversationView
  filter: StreamFilter | null
  names: string[]
  phonesTotal: number
  counts: Record<string, number> | undefined
  setView: (patch: Partial<ConversationView>) => void
}) {
  const { caseId, view, filter, names, phonesTotal, counts, setView } = props
  const key = view.people[0]
  const A = names[0] ?? key
  const B = view.people.length >= 2 ? (names[1] ?? view.people[1]) : "the owner of each phone"
  const linked = useQuery({
    queryKey: ["person-linked", caseId, key],
    queryFn: () => getLinkedIdentities(caseId, key),
    enabled: !!key,
    staleTime: 60_000,
  })
  // on how many of the case's phones A appears, whatever phone or dates are chosen (07 J-3 "on 4 of 14 phones")
  const across = useQuery({
    queryKey: ["person-phones", caseId, key],
    queryFn: () => getParticipants({ case_id: caseId, participants: [key], participant_mode: "any" }),
    enabled: !!key,
    staleTime: 60_000,
  })
  const phonesOn = across.data ? (across.data.items.find((p) => p.label.identity_key === key)?.phones.length ?? 0) : null
  const others = linked.data?.others.length ?? 0
  // the switch's effect: how many more rows the same scope holds with the other identities taken in
  const wider = useQuery({
    queryKey: ["person-wider", filter],
    queryFn: ({ signal }) => streamIndex({ ...filter!, expand_person_identities: true }, signal),
    enabled: !!filter && others > 0 && !view.expand,
    staleTime: 60_000,
  })
  const more = wider.data && counts ? Math.max(0, wider.data.counts.events - (counts.events ?? 0)) : null
  const self = key?.startsWith("phone:") ? 1 : 0
  const numbers = (linked.data?.numbers ?? 0) + self
  const accounts = (linked.data?.accounts ?? 0) + (key && !self ? 1 : 0)
  const between = view.mode === "between" && view.people.length <= 2
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>
        {A}
        {others > 0 ? ` (${plural(numbers, "number", "numbers")}, ${plural(accounts, "account", "accounts")})` : ""}
        {phonesOn !== null ? ` on ${fmt(phonesOn)} of ${plural(phonesTotal, "phone", "phones")}` : ""}
      </p>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="How to read A">
        {MODES.map((m) => (
          <button
            key={m.mode}
            type="button"
            aria-pressed={view.mode === m.mode}
            className="rounded border px-2 py-0.5 text-xs aria-pressed:bg-accent aria-pressed:font-medium"
            onClick={() => setView({ mode: m.mode })}
          >
            {m.words}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={view.allChannels}
          className="rounded border px-2 py-0.5 text-xs aria-pressed:bg-accent aria-pressed:font-medium"
          onClick={() => setView({ allChannels: !view.allChannels })}
        >
          All channels
        </button>
        <span className="text-xs text-muted-foreground">
          A is {A}. B is {B}.
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button
          type="button"
          role="switch"
          aria-checked={view.expand}
          aria-label="Include this person's other numbers and accounts"
          className="inline-flex items-center gap-1.5"
          onClick={() => setView({ expand: !view.expand })}
        >
          <span aria-hidden className={`inline-block h-3.5 w-6 rounded-full border ${view.expand ? "bg-primary" : "bg-muted"}`} />
          Include this person's other numbers and accounts
        </button>
        <span className="text-muted-foreground">
          {linked.isLoading
            ? "Looking for other numbers and accounts"
            : others === 0
              ? "No other number or account is linked to this person."
              : view.expand
                ? `Includes ${plural(others, "more number or account", "more numbers and accounts")}.`
                : `Include ${plural(others, "more number or account", "more numbers and accounts")}${more !== null ? ` (+${plural(more, "message", "messages")})` : ""}.`}
        </span>
      </div>
      {between && counts && (
        <p role="status">
          {plural(counts.messages ?? 0, "message", "messages")}
          {counts.calls ? ` and ${plural(counts.calls, "call", "calls")}` : ""} between {A} and {B} on {plural(counts.phones ?? 0, "phone", "phones")}
        </p>
      )}
    </div>
  )
}
