import { Switch } from "@/components/ui/switch"

import { DEEP_COST_NOTE } from "../deep-investigation"

/** Deep investigation for the next question: plan, work a checklist, check, then write a report. */
export function DeepSwitch({
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
        (checked ? "border-sky-500/40 bg-sky-500/10" : "border-border")
      }
      title={DEEP_COST_NOTE}
    >
      <Switch
        id="agent-deep"
        size="sm"
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        aria-label="Deep investigation"
      />
      <label htmlFor="agent-deep" className="whitespace-nowrap text-xs font-medium text-foreground">
        Deep investigation
      </label>
    </div>
  )
}
