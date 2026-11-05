import { RotateCcw } from "lucide-react"
import type { ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { PhoneChip } from "./PhoneChip"
import { ResultCount } from "./ResultCount"
import { EMPTY_SCOPE, MODE_WORDS, scopeWords, scopeToSearch } from "./scope"

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
  narrowed = false,
  children,
}: {
  scope: Scope
  onChange: (scope: Scope) => void
  /** null while the total is being counted: no number is stated until it is known (never "0 messages" for a
   * result still loading). */
  count: { shown: number; total: number; noun: string; unconfirmed?: number; soFar?: boolean } | null
  presets?: ScopePreset[]
  recent?: Scope[]
  /** Set when the scope was restored from this session: "Showing your last selection: 3 phones. Reset". */
  restored?: boolean
  /** Filters outside this bar narrow the result, so it is not "everything" even with no chip here. */
  narrowed?: boolean
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
        {empty && !narrowed && <span className="text-sm text-muted-foreground">Everything on every phone in this case</span>}
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
      {count ? (
        <ResultCount shown={count.shown} total={count.total} noun={count.noun} unconfirmed={count.unconfirmed} soFar={count.soFar} />
      ) : (
        <p role="status" className="text-sm text-muted-foreground" data-testid="result-count-pending">
          Counting
        </p>
      )}
    </div>
  )
}

export function Chip({ text, onRemove }: { text: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border bg-card px-1.5 py-0.5 text-xs font-medium">
      {text}
      <button type="button" onClick={onRemove} aria-label={`Remove ${text}`} className="rounded-sm px-0.5 text-muted-foreground hover:text-foreground">
        ×
      </button>
    </span>
  )
}
