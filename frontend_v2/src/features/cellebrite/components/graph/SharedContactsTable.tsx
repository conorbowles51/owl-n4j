import { Users } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"

import type { CellebriteRecord, RailSelection } from "../../types"
import { compactNumber, itemKey, readList, readNumber, readText } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { sharedContactSearchText } from "./graphUtils"

export function SharedContactsTable({
  rows,
  loading,
  search,
  onSelect,
}: {
  rows: CellebriteRecord[]
  loading: boolean
  search: string
  onSelect: (selection: RailSelection) => void
}) {
  const term = search.trim().toLowerCase()
  const visibleRows = term
    ? rows.filter((row) => sharedContactSearchText(row).toLowerCase().includes(term))
    : rows

  return (
    <section className="flex h-64 shrink-0 flex-col border-t border-border bg-background">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
        <Users className="size-4 text-amber-500" />
        <span className="text-xs font-semibold">Shared Contacts</span>
        {loading && <LoadingSpinner size="sm" className="ml-1" />}
        <Badge variant="slate" className="ml-auto">
          {compactNumber(visibleRows.length)}
        </Badge>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : visibleRows.length === 0 ? (
          <SmallEmpty label={rows.length === 0 ? "No shared contacts" : "No shared contacts match"} />
        ) : (
          <table className="w-full table-fixed text-left text-sm">
            <thead className="sticky top-0 z-10 bg-muted text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="border-b border-border px-3 py-2 font-semibold">Name</th>
                <th className="border-b border-border px-3 py-2 font-semibold">Reports</th>
                <th className="w-24 border-b border-border px-3 py-2 text-right font-semibold">Count</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, index) => {
                const key = itemKey(row, `shared-${index}`)
                const reports = readList(row, ["report_keys", "devices"]).join(", ") || "-"
                return (
                  <tr
                    key={`${key}-${index}`}
                    className={cn("cursor-pointer border-b border-border/70 transition-colors hover:bg-muted/50")}
                    onClick={() =>
                      onSelect({
                        id: key,
                        kind: "contact",
                        title: readText(row, ["name", "display_name", "label", "phone"], "Shared contact"),
                        payload: row,
                      })
                    }
                  >
                    <td className="truncate px-3 py-2 font-medium">
                      {readText(row, ["name", "display_name", "label", "phone"], "-")}
                    </td>
                    <td className="truncate px-3 py-2 text-muted-foreground">{reports}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {compactNumber(readNumber(row, ["count", "message_count", "total"]))}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
