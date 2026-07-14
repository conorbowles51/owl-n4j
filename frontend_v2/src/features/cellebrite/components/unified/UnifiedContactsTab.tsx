import { useMemo, useState } from "react"
import { ExternalLink, Filter, Loader2, Mail, MessageSquare, Phone, Search } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"
import { useUnifiedContacts } from "../../hooks/use-cellebrite"
import type { CellebriteRecord, PhoneReport, RailSelection } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import type { CommsSeed } from "../shared/cellebrite-types"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import { AliasChipGroup } from "./AliasChipGroup"
import {
  unifiedCallCount,
  unifiedDisplayNumber,
  unifiedEmailCount,
  unifiedInteractionCount,
  unifiedMatchesSearch,
  unifiedMessageCount,
  unifiedPersonKeys,
  unifiedReportKeys,
  unifiedContactId,
} from "./unifiedContactUtils"

export function UnifiedContactsTab({
  active,
  caseId,
  reportKeys,
  reports,
  query,
  onSelect,
  onFilterComms,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  reports: PhoneReport[]
  query: string
  onSelect: (selection: RailSelection) => void
  onFilterComms: (seed: CommsSeed) => void
}) {
  const [localSearch, setLocalSearch] = useState("")
  const [selectedCanonical, setSelectedCanonical] = useState<string | null>(null)
  const effectiveSearch = localSearch || query
  const contactsQuery = useUnifiedContacts(
    caseId,
    { reportKeys, limit: 1000 },
    active
  )
  const rows = useMemo(
    () => contactsQuery.data?.rows ?? contactsQuery.data?.contacts ?? [],
    [contactsQuery.data?.contacts, contactsQuery.data?.rows]
  )
  const filteredRows = useMemo(
    () => rows.filter((row) => unifiedMatchesSearch(row, effectiveSearch)),
    [effectiveSearch, rows]
  )
  const truncated = Boolean(contactsQuery.data?.truncated)
  const personCount = Number(contactsQuery.data?.person_count ?? 0)
  const personCap = Number(contactsQuery.data?.person_cap ?? personCount)

  const selectRow = (row: CellebriteRecord) => {
    const id = unifiedContactId(row)
    setSelectedCanonical(id)
    onSelect({
      id,
      kind: "contact_unified",
      title: unifiedDisplayNumber(row),
      payload: row,
    })
  }

  const filterComms = (row: CellebriteRecord) => {
    const personKeys = unifiedPersonKeys(row)
    if (!personKeys.length) return
    onFilterComms({
      id: `unified-contact-${unifiedContactId(row)}`,
      reportKeys: unifiedReportKeys(row),
      participantKeys: personKeys,
      type: "all",
      label: unifiedDisplayNumber(row),
    })
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Search className="size-4 text-muted-foreground" />
          <Input
            value={localSearch}
            onChange={(event) => setLocalSearch(event.target.value)}
            placeholder="Search by number or alias name..."
            className="h-8 max-w-xl"
          />
          <Badge variant="slate">
            {compactNumber(filteredRows.length)} / {compactNumber(rows.length)}
          </Badge>
        </div>
        {contactsQuery.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Building rollup
          </div>
        )}
      </div>

      {truncated && (
        <div className="shrink-0 border-b border-yellow-500/25 bg-yellow-500/10 px-4 py-1.5 text-[11px] text-yellow-800 dark:text-yellow-200">
          This case has at least {compactNumber(personCount)} contacts. The rollup was capped at {compactNumber(personCap)} by activity, so rare contacts may not appear here.
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        {contactsQuery.isLoading && rows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 size-4 animate-spin" />
            Building unified contacts rollup...
          </div>
        ) : contactsQuery.error ? (
          <div className="p-6 text-sm text-destructive">Failed to load unified contacts</div>
        ) : filteredRows.length === 0 ? (
          <SmallEmpty
            label={
              rows.length === 0
                ? "No contacts in this case yet."
                : "No contacts match the current search."
            }
          />
        ) : (
          <table className="w-full table-fixed text-sm">
            <thead className="sticky top-0 z-10 border-b border-border bg-muted text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="w-[180px] px-4 py-2 font-semibold">Number</th>
                <th className="px-4 py-2 font-semibold">Aliases used</th>
                <th className="w-[220px] px-4 py-2 font-semibold">Devices</th>
                <th className="w-20 px-4 py-2 text-right font-semibold">
                  <Phone className="mr-1 inline size-3" />Calls
                </th>
                <th className="w-20 px-4 py-2 text-right font-semibold">
                  <MessageSquare className="mr-1 inline size-3" />Msgs
                </th>
                <th className="w-20 px-4 py-2 text-right font-semibold">
                  <Mail className="mr-1 inline size-3" />Emails
                </th>
                <th className="w-36 px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row, index) => {
                const id = unifiedContactId(row)
                const selected = id === selectedCanonical
                const reportKeysForRow = unifiedReportKeys(row)
                return (
                  <tr
                    key={`${id}-${index}`}
                    onClick={() => selectRow(row)}
                    className={cn(
                      "cursor-pointer border-b border-border/70 transition-colors",
                      selected ? "bg-amber-50 dark:bg-amber-950/20" : "hover:bg-muted/50"
                    )}
                  >
                    <td className="px-4 py-2 font-mono text-foreground">
                      <span className={cn(!row.display_number && !row.canonical && "italic text-muted-foreground")}>
                        {unifiedDisplayNumber(row)}
                      </span>
                      {Boolean(row.is_phone_owner) && (
                        <Badge variant="success" className="ml-2 h-5 px-1.5 text-[9px] uppercase">
                          Owner
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <AliasChipGroup contact={row} />
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex flex-wrap gap-1">
                        {reportKeysForRow.length ? (
                          reportKeysForRow.map((reportKey) => (
                            <PhoneReportChip key={reportKey} reportKey={reportKey} reports={reports} />
                          ))
                        ) : (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {compactNumber(unifiedCallCount(row))}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {compactNumber(unifiedMessageCount(row))}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {compactNumber(unifiedEmailCount(row))}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={!unifiedPersonKeys(row).length}
                        title="Filter Comms feed by this number's aliases"
                        onClick={(event) => {
                          event.stopPropagation()
                          filterComms(row)
                        }}
                      >
                        <Filter className="size-3.5" />
                        Filter Comms
                        <ExternalLink className="size-3.5" />
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex h-7 shrink-0 items-center justify-between border-t border-border bg-card px-3 text-[10px] text-muted-foreground">
        <span>{compactNumber(filteredRows.length)} unified contacts displayed</span>
        <span>
          Sorted by owner status, then {compactNumber(filteredRows.reduce((sum, row) => sum + unifiedInteractionCount(row), 0))} total interactions
        </span>
      </div>
    </section>
  )
}
