import type { ReactNode } from "react"
import { InfoTip } from "./InfoTip"
import { FileSpreadsheet, FileSearch } from "lucide-react"

/**
 * Statement payments and other financial records are two separate sets. This
 * is a visible switch between them, never a collapsed line of text.
 */
export function RecordsModeSwitch({
  transactionsMode,
  onChange,
  aside,
}: {
  transactionsMode: boolean
  onChange: (mode: "transactions" | "intelligence") => void
  /** Shown on the same line, after the switch (the case access notice). */
  aside?: ReactNode
}) {
  const options = [
    {
      mode: "transactions" as const,
      label: "Statement payments",
      icon: FileSpreadsheet,
      active: transactionsMode,
    },
    {
      mode: "intelligence" as const,
      label: "Other financial records",
      icon: FileSearch,
      active: !transactionsMode,
    },
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b px-4 py-2">
      <div
        role="group"
        aria-label="Which financial records to show"
        className="inline-flex rounded-lg border bg-muted p-1"
      >
        {options.map(({ mode, label, icon: Icon, active }) => (
          <button
            key={mode}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(mode)}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <InfoTip text="Statement payments come from imported bank and card statements. Other financial records are amounts found elsewhere in case evidence; correcting a statement payment does not change them." />
      {aside}
    </div>
  )
}
