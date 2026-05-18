import { Mail, MessageSquare, Phone, Smartphone } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { CellebriteRecord, PhoneReport } from "../../types"
import { compactDate, compactNumber, readList } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { AliasChipGroup } from "./AliasChipGroup"
import {
  aliasName,
  unifiedAliases,
  unifiedCallCount,
  unifiedDisplayNumber,
  unifiedEmailCount,
  unifiedMessageCount,
  unifiedReportKeys,
} from "./unifiedContactUtils"

export function UnifiedContactDetail({
  contact,
  reports,
}: {
  contact: CellebriteRecord
  reports: PhoneReport[]
}) {
  const devicesIndex = new Map<string, string[]>()
  for (const alias of unifiedAliases(contact)) {
    for (const reportKey of readList(alias, ["report_keys"])) {
      const names = devicesIndex.get(reportKey) ?? []
      const name = aliasName(alias)
      if (name && !names.includes(name)) names.push(name)
      devicesIndex.set(reportKey, names)
    }
  }

  for (const reportKey of unifiedReportKeys(contact)) {
    if (!devicesIndex.has(reportKey)) devicesIndex.set(reportKey, [])
  }

  return (
    <div className="space-y-4 text-xs">
      <div>
        <div className="mb-2 flex items-center gap-2">
          <span className="font-mono text-sm font-semibold text-foreground">
            {unifiedDisplayNumber(contact)}
          </span>
          {Boolean(contact.is_phone_owner) && (
            <Badge variant="success" className="h-5 px-1.5 text-[9px] uppercase">
              Owner
            </Badge>
          )}
        </div>
        <AliasChipGroup contact={contact} />
      </div>

      <div className="grid grid-cols-3 gap-2">
        <CounterTile icon={Phone} label="Calls" value={unifiedCallCount(contact)} />
        <CounterTile icon={MessageSquare} label="Messages" value={unifiedMessageCount(contact)} />
        <CounterTile icon={Mail} label="Emails" value={unifiedEmailCount(contact)} />
      </div>

      {Boolean(contact.first_seen || contact.last_seen) && (
        <div className="border-t border-border pt-3 text-[11px] text-muted-foreground">
          {Boolean(contact.first_seen) && (
            <div>
              <span>First seen:</span>{" "}
              <span className="tabular-nums text-foreground">{compactDate(contact.first_seen)}</span>
            </div>
          )}
          {Boolean(contact.last_seen) && (
            <div>
              <span>Last seen:</span>{" "}
              <span className="tabular-nums text-foreground">{compactDate(contact.last_seen)}</span>
            </div>
          )}
        </div>
      )}

      {devicesIndex.size > 0 && (
        <div className="border-t border-border pt-3">
          <div className="mb-2 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <Smartphone className="size-3" />
            Per device
          </div>
          <ul className="space-y-2">
            {[...devicesIndex.entries()].map(([reportKey, names]) => (
              <li key={reportKey} className="flex items-center justify-between gap-2">
                <PhoneReportChip reportKey={reportKey} reports={reports} />
                <span className="min-w-0 flex-1 truncate text-right text-[11px] text-muted-foreground">
                  {names.length ? `Known as ${names.join(", ")}` : "Present on device"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function CounterTile({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Phone
  label: string
  value: number
}) {
  return (
    <div className="rounded-md border border-border bg-card px-2 py-1.5 text-center">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        <Icon className="mr-1 inline size-3" />
        {label}
      </div>
      <div className="text-base font-semibold tabular-nums text-foreground">
        {compactNumber(value)}
      </div>
    </div>
  )
}
