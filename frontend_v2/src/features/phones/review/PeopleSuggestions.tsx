import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { register } from "@/lib/keymap"
import { recordPath } from "@/lib/record-links"
import { LevelBadge } from "../analysis/MoneyPairings"
import { identitiesAPI, type IdentitySuggestion, type MatchLevel } from "./identities.api"
import { REASON_WORDS, standardReason, type LinkOrigin } from "./suggestion-reasons"
const fmt = (n: number) => n.toLocaleString("en-US")

function errorWords(e: unknown) {
  return e instanceof Error ? e.message : "Something went wrong."
}

/**
 * People suggestions (07 J-7): a docked, non-modal panel that steps through one suggestion at a time, strongest
 * first, with a filter by reason and by strength. Every suggestion is listed, faint ones too, each with its strength
 * by a stated rule and the reasons for it (how well matched, how substantiated). Each shows the name saved on each phone with its number, the reasons and
 * up to 3 example records per reason with their counts. Keys: y Link, x Not the same person, s Skip, j/k move.
 */
export function PeopleSuggestions({ caseId, origin = "review" }: { caseId: string; origin?: LinkOrigin }) {
  const client = useQueryClient()
  const sugg = useQuery({ queryKey: ["phone-identity-suggestions", caseId], queryFn: () => identitiesAPI.suggestions(caseId) })
  const [reason, setReason] = useState("")
  const [level, setLevel] = useState<"" | MatchLevel>("")
  const [at, setAt] = useState(0)
  const [name, setName] = useState("")
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const all = useMemo(() => sugg.data?.suggestions ?? [], [sugg.data])
  const reasons = useMemo(() => [...new Set(all.flatMap((s) => s.reasons.map((r) => r.reason)))].sort(), [all])
  const list = useMemo(
    () => all.filter((s) => (!reason || s.reasons.some((r) => r.reason === reason)) && (!level || s.level === level)),
    [all, reason, level],
  )
  const byLevel = sugg.data?.by_level
  const s = list[Math.min(at, Math.max(0, list.length - 1))] as IdentitySuggestion | undefined
  const details = useQueries({
    queries: (s?.identities ?? []).map((i) => ({
      queryKey: ["phone-identity", caseId, i.identity_key],
      queryFn: () => identitiesAPI.get(caseId, i.identity_key),
    })),
  })
  // the new person's name starts as the name a phone saved most often for these identities; a person edits it
  const suggestedName = useMemo(() => {
    const names = details.flatMap((d) => d.data?.names ?? []).filter((n) => n.is_phone_name)
    names.sort((a, b) => b.occurrences - a.occurrences)
    return names[0]?.name ?? ""
  }, [details])
  useEffect(() => setName(suggestedName), [suggestedName, s?.id])

  const decided = sugg.data?.decided ?? 0
  const total = decided + all.length
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["phone-identity-suggestions", caseId] })
    for (const i of s?.identities ?? []) await client.invalidateQueries({ queryKey: ["phone-identity", caseId, i.identity_key] })
    await client.invalidateQueries({ queryKey: ["dossiers", caseId] })
  }
  const run = async (body: Parameters<typeof identitiesAPI.decide>[1], words: string) => {
    if (busy || !s) return
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      await identitiesAPI.decide(caseId, body)
      setDone(words)
      setNote("")
    } catch (e) {
      setError(errorWords(e))
    } finally {
      await refresh()
      setBusy(false)
    }
  }
  const link = () => {
    if (!s) return
    if (!s.dossier_id && !name.trim()) {
      setError("Type the person's name first.")
      return
    }
    void run(
      {
        decision: "link_phone_identity",
        identity_keys: s.identities.map((i) => i.identity_key),
        ...(s.dossier_id ? { dossier_id: s.dossier_id } : { new_person_name: name.trim() }),
        reasons_shown: s.reasons.map((r) => ({ reason: r.reason })),
        origin,
        note: note.trim() || undefined,
        expected_revision: s.expected_revision,
      },
      s.dossier_id ? "Linked to the person on the dossier." : `Linked as one person, ${name.trim()}.`,
    )
  }
  const reject = () => {
    if (!s) return
    const [first, ...rest] = s.identities
    void run(
      {
        decision: "reject_phone_identity_link",
        identity_keys: [first.identity_key],
        ...(s.dossier_id ? { dossier_id: s.dossier_id } : rest[0] ? { target_identity_key: rest[0].identity_key } : {}),
        expected_revision: s.expected_revision,
      },
      "Marked as not the same person. It will not be suggested again.",
    )
  }
  const move = (d: number) => setAt((i) => Math.max(0, Math.min(list.length - 1, i + d)))

  useEffect(
    () =>
      register("People suggestions", [
        { key: "y", label: "Link", run: link },
        { key: "x", label: "Not the same person", run: reject },
        { key: "s", label: "Skip", run: () => move(1) },
        { key: "j", label: "Next suggestion", run: () => move(1) },
        { key: "k", label: "Previous suggestion", run: () => move(-1) },
      ]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [s?.id, s?.expected_revision, s?.dossier_id, name, note, busy, list.length],
  )

  return (
    <aside aria-labelledby="people-suggestions" className="flex flex-col gap-3 rounded border bg-card p-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="people-suggestions" className="text-base font-semibold">People suggestions</h2>
        <span role="status" className="text-sm">{fmt(decided)} of {fmt(total)} decided</span>
        {reasons.length > 1 && (
          <label className="flex items-center gap-1 text-sm">
            Reason
            <select value={reason} onChange={(e) => { setReason(e.target.value); setAt(0) }} className="rounded border bg-background px-1 py-0.5">
              <option value="">All reasons</option>
              {reasons.map((r) => (
                <option key={r} value={r}>{REASON_WORDS[r] ?? r}</option>
              ))}
            </select>
          </label>
        )}
        {byLevel && all.length > 0 && (
          <label className="flex items-center gap-1 text-sm">
            Strength
            <select value={level} onChange={(e) => { setLevel(e.target.value as "" | MatchLevel); setAt(0) }} className="rounded border bg-background px-1 py-0.5">
              <option value="">Every strength</option>
              {(["strong", "moderate", "weak", "faint"] as const).map((lv) => (
                <option key={lv} value={lv}>{`${lv[0].toUpperCase()}${lv.slice(1)} (${fmt(byLevel[lv] ?? 0)})`}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {sugg.data?.scale && all.length > 0 && <p className="text-xs text-muted-foreground">{sugg.data.scale}</p>}
      {sugg.isLoading && <p role="status" className="text-sm">Loading the suggestions.</p>}
      {sugg.isError && <p role="alert" className="text-sm">The suggestions could not be loaded. {errorWords(sugg.error)}</p>}
      {sugg.data && !s && <p className="text-sm">No suggestions are waiting. New ones appear when a phone is added or a dossier gains a contact detail.</p>}
      {s && (
        <>
          <p className="text-sm text-muted-foreground">
            Suggestion {fmt(Math.min(at, list.length - 1) + 1)} of {fmt(list.length)}, strongest first.
          </p>
          {s.level && (
            <div aria-label="Strength" className="flex flex-col gap-1 text-sm">
              <p className="flex items-center gap-2"><LevelBadge level={s.level} /> match</p>
              {s.strength_reasons && (
                <ul className="pl-3 text-xs text-muted-foreground">
                  <li>How well matched: {s.strength_reasons.match.join("; ")}</li>
                  <li>How substantiated: {s.strength_reasons.substantiation.join("; ") || "nothing beyond the match"}</li>
                </ul>
              )}
            </div>
          )}
          <ul aria-label="Names on each phone" className="flex flex-col gap-1 text-sm">
            {s.identities.map((i, k) => {
              const d = details[k]?.data
              return (
                <li key={i.identity_key}>
                  <span className="font-medium">{i.value_display}</span>
                  {d && d.names.length > 0
                    ? `: ${d.names.filter((n) => n.is_phone_name).map((n) => `${n.phone ?? "a phone"} saves it as ${n.name}`).join("; ") || "no phone saves a name for it"}`
                    : d ? ": no phone saves a name for it" : ""}
                </li>
              )
            })}
          </ul>
          <section aria-label="Reasons" className="flex flex-col gap-1 text-sm">
            <h3 className="font-medium">Reasons</h3>
            {s.reasons.map((r) => (
              <div key={r.reason}>
                <p>
                  {REASON_WORDS[r.reason] ?? r.reason}
                  {r.names?.length ? ` (${r.names.join(", ")})` : ""}
                  {r.phones.length ? ` (on ${r.phones.join(", ")})` : ""}
                  {r.reason === "name_only" ? "" : `: ${fmt(r.record_count)} ${r.record_count === 1 ? "record" : "records"}`}
                </p>
                {r.records.length > 0 && (
                  <ul className="flex flex-wrap gap-2 pl-3 text-xs">
                    {r.records.slice(0, 3).map((uid, n) => (
                      <li key={uid}>
                        <Link className="underline" to={recordPath(caseId, uid)}>Example {n + 1}</Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </section>
          {!s.dossier_id && (
            <label className="flex flex-col gap-1 text-sm">
              Name for the new person
              <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border bg-background px-2 py-1" />
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm">
            Note (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} className="rounded border bg-background px-2 py-1" />
          </label>
          <p className="text-xs text-muted-foreground">The link stores this reason: {standardReason(s, origin)}.</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={link} disabled={busy}>Link (y)</Button>
            <Button size="sm" variant="outline" onClick={reject} disabled={busy}>Not the same person (x)</Button>
            <Button size="sm" variant="ghost" onClick={() => move(1)} disabled={busy}>Skip (s)</Button>
          </div>
        </>
      )}
      {done && <p role="status" className="text-sm">{done}</p>}
      {error && <p role="alert" className="text-sm">{error}</p>}
    </aside>
  )
}
