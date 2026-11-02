import { RotateCcw } from "lucide-react"
import type { ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { PhoneChip } from "./PhoneChip"
import { ResultCount } from "./ResultCount"

/**
 * One scope, carried everywhere (07 4.5): people, phones, window, labels and kinds as removable chips with the
 * resulting count; presets ("Phones of <dossier>", "Phones where <person> appears", the last 5 scopes); the scope
 * lives in the URL and is remembered per case for the session.
 */
export type ParticipantMode = "involving" | "between" | "sent-by" | "sent-to"

export interface Scope {
  people: { key: string; label: string }[]
  mode: ParticipantMode
  phones: { id: string; label: string; index: number; extractionDate?: string }[]
  window: { from: string; to: string } | null
  labels: { id: string; label: string }[]
  kinds: string[]
}

export const EMPTY_SCOPE: Scope = { people: [], mode: "involving", phones: [], window: null, labels: [], kinds: [] }

const MODE_WORDS: Record<ParticipantMode, string> = {
  involving: "Involving",
  between: "Between",
  "sent-by": "Sent by",
  "sent-to": "Sent to",
}

export function scopeWords(scope: Scope): string {
  const parts: string[] = []
  if (scope.people.length) {
    const names = scope.people.map((p) => p.label)
    parts.push(scope.mode === "between" ? `between ${names.join(" and ")}` : `${MODE_WORDS[scope.mode].toLowerCase()} ${names.join(", ")}`)
  }
  if (scope.window) parts.push(`${scope.window.from} to ${scope.window.to}`)
  if (scope.phones.length) parts.push(`on ${scope.phones.length} ${scope.phones.length === 1 ? "phone" : "phones"}`)
  if (scope.labels.length) parts.push(`labelled ${scope.labels.map((l) => l.label).join(", ")}`)
  if (scope.kinds.length) parts.push(scope.kinds.join(", "))
  return parts.join(", ") || "everything on every phone"
}

/** URL form (ids only; labels are looked up again on load). */
export function scopeToSearch(scope: Scope): string {
  const q = new URLSearchParams()
  if (scope.people.length) q.set("people", scope.people.map((p) => p.key).join(","))
  if (scope.mode !== "involving") q.set("mode", scope.mode)
  if (scope.phones.length) q.set("phones", scope.phones.map((p) => p.id).join(","))
  if (scope.window) q.set("window", `${scope.window.from}..${scope.window.to}`)
  if (scope.labels.length) q.set("labels", scope.labels.map((l) => l.id).join(","))
  if (scope.kinds.length) q.set("kinds", scope.kinds.join(","))
  return q.toString()
}

export function searchToScopeIds(search: string) {
  const q = new URLSearchParams(search)
  const list = (k: string) => (q.get(k) ? q.get(k)!.split(",").filter(Boolean) : [])
  const [from, to] = (q.get("window") ?? "").split("..")
  return {
    people: list("people"),
    mode: (q.get("mode") as ParticipantMode) ?? "involving",
    phones: list("phones"),
    window: from && to ? { from, to } : null,
    labels: list("labels"),
    kinds: list("kinds"),
  }
}

/** Remembered per case for the session; storage failures never break the page (07 4.2 item 13). */
export function rememberScope(caseId: string, scope: Scope) {
  try {
    sessionStorage.setItem(`phone-scope:${caseId}`, JSON.stringify(scope))
    const recentKey = `phone-scope-recent:${caseId}`
    const recent: Scope[] = JSON.parse(sessionStorage.getItem(recentKey) ?? "[]")
    const key = scopeToSearch(scope)
    const next = [scope, ...recent.filter((s) => scopeToSearch(s) !== key)].slice(0, 5)
    sessionStorage.setItem(recentKey, JSON.stringify(next))
  } catch {
    /* storage unavailable: the URL still carries the scope */
  }
}

export function recallScope(caseId: string): { last: Scope | null; recent: Scope[] } {
  try {
    const last = sessionStorage.getItem(`phone-scope:${caseId}`)
    const recent = sessionStorage.getItem(`phone-scope-recent:${caseId}`)
    return { last: last ? JSON.parse(last) : null, recent: recent ? JSON.parse(recent) : [] }
  } catch {
    return { last: null, recent: [] }
  }
}

export interface ScopePreset {
  label: string
  scope: Scope
}

export function ScopeBar({
  scope,
  onChange,
  count,
  presets = [],
  recent = [],
  restored,
  children,
}: {
  scope: Scope
  onChange: (scope: Scope) => void
  count: { shown: number; total: number; noun: string; unconfirmed?: number; soFar?: boolean }
  presets?: ScopePreset[]
  recent?: Scope[]
  /** Set when the scope was restored from this session: "Showing your last selection: 3 phones. Reset". */
  restored?: boolean
  /** More of the scope in words and controls, inside the same region (07 J-3: the chosen person). */
  children?: ReactNode
}) {
  const remove = (patch: Partial<Scope>) => onChange({ ...scope, ...patch })
  const empty = scopeToSearch(scope) === ""
  return (
    <div role="region" aria-label="Scope" className="flex flex-col gap-1 border-b bg-card px-3 py-2 text-foreground" data-testid="scope-bar">
      {restored && !empty && (
        <p className="text-sm" role="status">
          Showing your last selection: {scopeWords(scope)}.{" "}
          <button type="button" className="underline underline-offset-2" onClick={() => onChange(EMPTY_SCOPE)}>
            Reset
          </button>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        {scope.people.length > 0 && (
          <label className="inline-flex items-center gap-1 text-sm">
            <span className="sr-only">Who</span>
            <select
              className="rounded border bg-card px-1 py-0.5 text-sm"
              value={scope.mode}
              onChange={(e) => onChange({ ...scope, mode: e.target.value as ParticipantMode })}
              aria-label="Participant mode"
            >
              {(Object.keys(MODE_WORDS) as ParticipantMode[]).map((m) => (
                <option key={m} value={m}>
                  {MODE_WORDS[m]}
                </option>
              ))}
            </select>
          </label>
        )}
        {scope.people.map((p) => (
          <Chip key={p.key} text={p.label} onRemove={() => remove({ people: scope.people.filter((x) => x.key !== p.key) })} />
        ))}
        {scope.phones.map((ph) => (
          <PhoneChip
            key={ph.id}
            label={ph.label}
            index={ph.index}
            extractionDate={ph.extractionDate}
            collides={scope.phones.filter((x) => x.label === ph.label).length > 1}
            onRemove={() => remove({ phones: scope.phones.filter((x) => x.id !== ph.id) })}
          />
        ))}
        {scope.window && <Chip text={`${scope.window.from} to ${scope.window.to}`} onRemove={() => remove({ window: null })} />}
        {scope.labels.map((l) => (
          <Chip key={l.id} text={`Label: ${l.label}`} onRemove={() => remove({ labels: scope.labels.filter((x) => x.id !== l.id) })} />
        ))}
        {scope.kinds.map((k) => (
          <Chip key={k} text={k} onRemove={() => remove({ kinds: scope.kinds.filter((x) => x !== k) })} />
        ))}
        {empty && <span className="text-sm text-muted-foreground">Everything on every phone in this case</span>}
        {(presets.length > 0 || recent.length > 0) && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline">
                Presets
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {presets.map((p) => (
                <DropdownMenuItem key={p.label} onSelect={() => onChange(p.scope)}>
                  {p.label}
                </DropdownMenuItem>
              ))}
              {recent.length > 0 && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Your last {recent.length} scopes</DropdownMenuLabel>
                  {recent.map((s) => (
                    <DropdownMenuItem key={scopeToSearch(s)} onSelect={() => onChange(s)}>
                      {scopeWords(s)}
                    </DropdownMenuItem>
                  ))}
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {!empty && (
          <Button size="sm" variant="ghost" onClick={() => onChange(EMPTY_SCOPE)}>
            <RotateCcw className="size-3.5" aria-hidden /> Reset
          </Button>
        )}
      </div>
      {children}
      <ResultCount shown={count.shown} total={count.total} noun={count.noun} unconfirmed={count.unconfirmed} soFar={count.soFar} />
    </div>
  )
}

function Chip({ text, onRemove }: { text: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border bg-card px-1.5 py-0.5 text-xs font-medium">
      {text}
      <button type="button" onClick={onRemove} aria-label={`Remove ${text}`} className="rounded-sm px-0.5 text-muted-foreground hover:text-foreground">
        ×
      </button>
    </span>
  )
}
