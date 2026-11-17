import { CommandGroup, CommandItem } from "@/components/ui/command"
import type { MeaningResult } from "../api"

/** The areas of the search by meaning, in the words a person uses. */
const MEANING_AREAS: Record<string, string> = {
  phone_text: "Phone messages",
  ledger: "Payments",
  accounts: "Accounts",
  judgements: "Judgement calls",
  trails: "Saved money groups",
  statement_pages: "Statement pages",
  casework: "Notes, findings and theories",
  timeline: "Timeline",
  parties: "People and names on the phones",
  transcripts: "Transcripts and image text",
  relationships: "Connections in the graph",
  entities: "People, companies and places in the graph",
  documents: "Documents",
}
const MEANING_WHY: Record<string, string> = { meaning: "by meaning", words: "by words", both: "by meaning and words" }

/** The hits found by meaning and words together, each saying which found it, and what was not searched. */
export default function MeaningGroup({ meaning, error, onOpen }: { meaning: MeaningResult | undefined; error: string | null; onOpen: (cite: string) => void }) {
  if (error) return <p role="alert" className="px-4 pt-3 text-xs">{error}</p>
  if (!meaning) return <p className="px-4 pt-3 text-xs text-muted-foreground">Searching by meaning</p>
  return (
    <CommandGroup heading={`By meaning (${meaning.hits.length.toLocaleString("en-US")})`}>
      {meaning.hits.map((h) => (
        <CommandItem key={`meaning:${h.area}:${h.key}`} value={`meaning:${h.area}:${h.key}`} onSelect={() => onOpen(h.cite)}>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="truncate text-xs text-muted-foreground">
              {[MEANING_AREAS[h.area] ?? h.area, MEANING_WHY[h.matched], h.as_read ? "read by a model, not confirmed" : null, h.title].filter(Boolean).join(" · ")}
            </span>
            <span className="line-clamp-2 text-sm">{h.snippet.replace(/ \[rec:\/\/[0-9a-f-]{36}\]/g, "")}</span>
          </span>
        </CommandItem>
      ))}
      {meaning.hits.length === 0 && <p className="px-2 pb-1 text-xs">Nothing found by meaning.</p>}
      {meaning.notes.map((n) => (
        <p key={n} role="note" className="px-2 pb-1 text-xs">{n}</p>
      ))}
      {meaning.not_searched.length > 0 && <p className="px-2 pb-1 text-xs text-muted-foreground">Not searched: {meaning.not_searched.join("; ")}.</p>}
    </CommandGroup>
  )
}
