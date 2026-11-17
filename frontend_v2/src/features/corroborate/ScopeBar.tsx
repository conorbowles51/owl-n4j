import { scopeIsEmpty, type Preview, type Scope } from "./api"

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
const KIND_WORDS: Record<string, string> = {
  phone_record: "phone records", financial_transaction: "payments", evidence: "documents", graph_entity: "graph items",
  timeline_event: "timeline events", financial_account: "accounts", financial_party: "parties", place: "areas", entry: "notes",
}

/**
 * The scope bar (lx-corroselect D, P): time, a recurring window, record kinds and people, each a removable chip with a
 * live count, and always a sentence on what is outside the scope, per kind. The zone is named. Nothing is removed from
 * the selection; the scope only chooses what the question is asked of.
 */
export function ScopeBar({ scope, onChange, preview }: { scope: Scope; onChange: (s: Scope) => void; preview: Preview }) {
  const zone = scope.zone ?? "UTC"
  const kinds = preview.taken.items.map((i) => i.type)
  const set = (patch: Partial<Scope>) => onChange({ ...scope, ...patch })
  const chips = preview.scope.words
  return (
    <details className="rounded border px-2 py-1 text-sm" open={!scopeIsEmpty(scope)}>
      <summary className="cursor-pointer font-medium">
        Scope{chips.length ? `: ${chips.length} filter${chips.length === 1 ? "" : "s"}, ${preview.members.toLocaleString("en-US")} of ${preview.selected.toLocaleString("en-US")} items in scope` : " (everything selected)"}
      </summary>
      <div className="mt-1 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="flex flex-col text-xs text-muted-foreground">From
          <input type="date" className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={scope.from ?? ""} onChange={(e) => set({ from: e.target.value || undefined })} />
        </label>
        <label className="flex flex-col text-xs text-muted-foreground">To
          <input type="date" className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={scope.to ?? ""} onChange={(e) => set({ to: e.target.value || undefined })} />
        </label>
        <label className="flex flex-col text-xs text-muted-foreground">Time zone
          <input className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={zone} onChange={(e) => set({ zone: e.target.value || undefined })} />
        </label>
        <div className="flex flex-col text-xs text-muted-foreground">
          Repeats
          <div className="flex flex-wrap items-center gap-1">
            <select aria-label="Day of the week" className="rounded border bg-card px-1 py-1 text-sm text-foreground"
              value={scope.recurring ? String(scope.recurring.weekday ?? "") : "off"}
              onChange={(e) => e.target.value === "off" ? set({ recurring: undefined }) : set({ recurring: { weekday: e.target.value === "" ? null : Number(e.target.value), from_hour: scope.recurring?.from_hour ?? 22, to_hour: scope.recurring?.to_hour ?? 4 } })}>
              <option value="off">Not recurring</option>
              <option value="">Every day</option>
              {DAYS.map((d, i) => <option key={d} value={i}>Every {d}</option>)}
            </select>
            {scope.recurring && (
              <>
                <input aria-label="From hour" type="number" min={0} max={23} className="w-14 rounded border bg-card px-1 py-1 text-sm text-foreground" value={scope.recurring.from_hour}
                  onChange={(e) => set({ recurring: { ...scope.recurring!, from_hour: Number(e.target.value) } })} />
                <span>to</span>
                <input aria-label="To hour" type="number" min={0} max={24} className="w-14 rounded border bg-card px-1 py-1 text-sm text-foreground" value={scope.recurring.to_hour}
                  onChange={(e) => set({ recurring: { ...scope.recurring!, to_hour: Number(e.target.value) } })} />
                <span>({zone})</span>
              </>
            )}
          </div>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={!!scope.relative}
            onChange={(e) => set({ relative: e.target.checked ? { anchor_kind: "financial_transaction", before_min: 30, after_min: 0 } : undefined })} />
          Around each payment
        </label>
        {scope.relative && (
          <>
            <input aria-label="Minutes before" type="number" min={0} className="w-16 rounded border bg-card px-1 py-1 text-sm text-foreground" value={scope.relative.before_min}
              onChange={(e) => set({ relative: { ...scope.relative!, before_min: Number(e.target.value) } })} />
            <span>min before,</span>
            <input aria-label="Minutes after" type="number" min={0} className="w-16 rounded border bg-card px-1 py-1 text-sm text-foreground" value={scope.relative.after_min}
              onChange={(e) => set({ relative: { ...scope.relative!, after_min: Number(e.target.value) } })} />
            <span>min after, to</span>
            <input aria-label="Payments to this person" placeholder="anyone" className="w-28 rounded border bg-card px-1 py-1 text-sm text-foreground" value={scope.relative.person ?? ""}
              onChange={(e) => set({ relative: { ...scope.relative!, person: e.target.value || undefined } })} />
          </>
        )}
      </div>
      {preview.scope.anchors !== null && scope.relative && (
        <p role="status" className="text-xs">
          {preview.scope.anchors.toLocaleString("en-US")} {preview.scope.anchors === 1 ? "payment has" : "payments have"} a time to hang the window on.
          {preview.scope.anchors_date_only > 0 && ` ${preview.scope.anchors_date_only.toLocaleString("en-US")} ${preview.scope.anchors_date_only === 1 ? "has" : "have"} only a date, so a window of minutes cannot be placed round ${preview.scope.anchors_date_only === 1 ? "it" : "them"}.`}
        </p>
      )}
      <fieldset className="mt-1 flex flex-wrap gap-2 text-xs">
        <legend className="text-muted-foreground">Record kinds</legend>
        {kinds.map((k) => (
          <label key={k} className="flex items-center gap-1">
            <input type="checkbox" checked={scope.kinds?.includes(k) ?? false}
              onChange={(e) => { const next = new Set(scope.kinds ?? []); if (e.target.checked) next.add(k); else next.delete(k); set({ kinds: next.size ? [...next] : undefined }) }} />
            {KIND_WORDS[k] ?? k.replace(/_/g, " ")} ({preview.taken.items.find((i) => i.type === k)?.count.toLocaleString("en-US")})
          </label>
        ))}
      </fieldset>
      <label className="mt-1 flex flex-col text-xs text-muted-foreground">People (names, comma separated)
        <input className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={(scope.people ?? []).join(", ")}
          onChange={(e) => { const v = e.target.value.split(",").map((x) => x.trim()).filter(Boolean); set({ people: v.length ? v : undefined }) }} />
      </label>
      {chips.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-1 text-xs">
          {chips.map((c) => <li key={c} className="rounded border bg-muted px-2 py-0.5">{c}</li>)}
          <li><button type="button" className="underline" onClick={() => onChange({})}>Clear the scope</button></li>
        </ul>
      )}
      {preview.scope.active && (
        <p role="status" className="mt-1 text-xs">
          Outside the scope: {preview.scope.outside_total === 0 ? "nothing" : Object.entries(preview.scope.outside).map(([k, n]) => `${n.toLocaleString("en-US")} ${KIND_WORDS[k] ?? k.replace(/_/g, " ")}`).join(", ")}.
          {preview.scope.no_time > 0 && ` ${preview.scope.no_time.toLocaleString("en-US")} items have no time, so a time rule cannot place them; they stay in.`}
        </p>
      )}
    </details>
  )
}
