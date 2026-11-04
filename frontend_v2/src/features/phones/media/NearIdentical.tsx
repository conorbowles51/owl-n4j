import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { recordPath } from "@/lib/record-links"
import { getMediaSpreadPerceptual, type PerceptualCopy } from "../api"
import { hashingWords } from "./near-identical-words"
import { LEVELS, LEVEL_WORDS, levelCountWords } from "../analysis/strength-words"

const n = (v: number) => v.toLocaleString("en-US")
const PAGE = 50
const ROLE: Record<string, string> = { sent: "sent", received: "received", direction_unknown: "direction not recorded" }

function Copy({ caseId, c, onOpen }: { caseId: string; c: PerceptualCopy; onOpen: (uid: string) => void }) {
  return (
    <span className="flex flex-col">
      <span><span className="font-medium">{c.phone_label}</span>: <button type="button" className="break-all underline" onClick={() => onOpen(c.file_uid)}>Open {c.filename}</button>
        {c.copies_on_phone > 1 ? ` (${n(c.copies_on_phone)} copies on this phone)` : ""}; {c.roles.length ? c.roles.map((r) => ROLE[r] ?? r).join(" and ") : "not carried by a message"}</span>
      {c.messages.map((m) => (
        <span key={m.message_record_uid} className="ml-3">
          <Link className="underline" to={recordPath(caseId, m.message_record_uid)}>{m.role === "sent" ? "Sent" : m.role === "received" ? "Received" : "Carried"}{m.app ? ` on ${m.app}` : ""}</Link> {m.full}{m.deleted ? " (message marked deleted)" : ""}
        </span>
      ))}
      {c.messages_total > c.messages.length && <span className="ml-3">{n(c.messages.length)} of {n(c.messages_total)} messages shown.</span>}
    </span>
  )
}

/** Near-identical pictures across phones (05 section 11.3 step 3), every pair graded strong to faint, with reasons. */
export function NearIdentical({ caseId, onOpen }: { caseId: string; onOpen: (uid: string) => void }) {
  const [strength, setStrength] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const q = useQuery({ queryKey: ["phone-media-spread-perceptual", caseId, strength, offset], queryFn: () => getMediaSpreadPerceptual(caseId, strength, offset, PAGE), enabled: !!caseId })
  const p = q.data
  return (
    <section aria-label="Near-identical pictures" className="flex flex-col gap-2 border-t pt-3" data-testid="near-identical">
      <h2 className="font-semibold">Near-identical pictures</h2>
      {q.isError && <p role="alert">The near-identical pictures could not be loaded.</p>}
      {p && (
        <>
          <p className="text-xs">{p.words}</p>
          <p role="status" className="font-medium" data-testid="near-identical-counts">{levelCountWords(p.by_strength, ["near-identical pair", "near-identical pairs"])}</p>
          <p className="text-xs" data-testid="near-identical-thin">{hashingWords(p)} The plan first offered this only once a sample of 20 forwarded pictures showed exact matching failing on a quarter of them; every pair is listed here with its strength, however few there are.</p>
          <p className="text-xs text-muted-foreground">{p.rule_words}</p>
          {p.stopped_words && <p role="note" className="font-medium">{p.stopped_words}</p>}
          <div className="flex flex-wrap gap-2 text-xs" role="tablist">
            <Button size="sm" role="tab" aria-selected={strength === null} variant={strength === null ? "primary" : "outline"} onClick={() => { setStrength(null); setOffset(0) }}>All ({n(p.total_all)})</Button>
            {LEVELS.map((l) => (
              <Button key={l} size="sm" role="tab" aria-selected={strength === l} variant={strength === l ? "primary" : "outline"} onClick={() => { setStrength(l); setOffset(0) }}>{LEVEL_WORDS[l]} ({n(p.by_strength[l] ?? 0)})</Button>
            ))}
          </div>
          <p role="status" className="text-xs">{p.total === 0 ? "No pairs match." : `Showing ${n(offset + 1)} to ${n(offset + p.items.length)} of ${n(p.total)} ${p.total === 1 ? "pair" : "pairs"}.`}</p>
          <ul aria-label="Near-identical pairs" className="flex flex-col gap-2">
            {p.items.map((it) => (
              <li key={`${it.a.file_uid}-${it.b.file_uid}`} className="flex flex-col gap-1 rounded border p-2 text-xs" data-testid="near-identical-pair">
                <span><span className="rounded bg-muted px-1">{it.label}</span> <span className="font-medium">{LEVEL_WORDS[it.level]}</span>: {[...it.reasons.match, ...it.reasons.substantiation].join(" ")}</span>
                <Copy caseId={caseId} c={it.a} onOpen={onOpen} />
                <Copy caseId={caseId} c={it.b} onOpen={onOpen} />
              </li>
            ))}
          </ul>
          {p.total > PAGE && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
              <Button size="sm" variant="outline" disabled={offset + PAGE >= p.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
            </div>
          )}
          <p className="text-xs text-muted-foreground">{p.clock_words}</p>
        </>
      )}
    </section>
  )
}
