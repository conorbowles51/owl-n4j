import type { CellebriteRecord } from "../../types"
import { compactNumber, readList } from "../shared/cellebrite-format"
import { aliasKey, aliasName, unifiedAliases } from "./unifiedContactUtils"

export function AliasChipGroup({ contact }: { contact: CellebriteRecord }) {
  const aliases = unifiedAliases(contact)
  const truncatedBy = Number(contact.aliases_truncated_by ?? 0)

  if (!aliases.length) return <span className="text-muted-foreground">-</span>

  return (
    <div className="flex flex-wrap gap-1">
      {aliases.map((alias, index) => {
        const reportKeys = readList(alias, ["report_keys"])
        return (
          <span
            key={aliasKey(alias, `alias-${index}`)}
            className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
            title={
              reportKeys.length
                ? `Used on ${reportKeys.length} device${reportKeys.length === 1 ? "" : "s"}`
                : aliasKey(alias, `alias-${index}`)
            }
          >
            {aliasName(alias)}
            {reportKeys.length > 1 && (
              <span className="ml-1 text-[9px] text-muted-foreground">x{reportKeys.length}</span>
            )}
          </span>
        )
      })}
      {truncatedBy > 0 && (
        <span className="inline-flex items-center rounded bg-amber-500/15 px-1.5 py-0.5 text-[11px] text-amber-700">
          +{compactNumber(truncatedBy)} more
        </span>
      )}
    </div>
  )
}
