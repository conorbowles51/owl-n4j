import { Switch } from "@/components/ui/switch"

/** The all-cases switch: the agent reads every case the person can open, for this conversation only. */
export function AllCasesSwitch({
  checked,
  disabled,
  onCheckedChange,
}: {
  checked: boolean
  disabled?: boolean
  onCheckedChange: (value: boolean) => void
}) {
  return (
    <div
      className={
        "flex shrink-0 items-center gap-2 rounded-md border px-2 py-1 " +
        (checked ? "border-amber-500/40 bg-amber-500/10" : "border-border")
      }
      title={
        disabled
          ? "All cases is unavailable while the agent reads only the Significant layer."
          : "When on, the agent may read every case you can open, for this conversation. Each record it cites " +
            "from another case names that case. A new conversation starts with this off."
      }
    >
      <Switch
        id="agent-all-cases"
        size="sm"
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        aria-label="All my cases"
      />
      <label htmlFor="agent-all-cases" className="whitespace-nowrap text-xs font-medium text-foreground">
        {checked ? "Reading all my cases" : "This case only"}
      </label>
    </div>
  )
}
