import type { AgentModelChoice } from "../types"

/**
 * The model choice beside the send box (AG-08): pick a stronger model or longer thinking for the next message, mid
 * conversation. Each answer shows which model wrote it.
 */
export function AgentModelPicker({
  choices,
  value,
  onChange,
  disabled,
}: {
  choices: AgentModelChoice[]
  value: string | null
  onChange: (key: string) => void
  disabled?: boolean
}) {
  if (choices.length < 2) return null
  const current = value ?? choices.find((choice) => choice.default)?.key ?? choices[0]?.key
  return (
    <select
      aria-label="Model for the next message"
      title="Model for the next message"
      className="h-9 max-w-44 shrink-0 rounded-md border border-border bg-background px-2 text-xs text-foreground"
      value={current}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
    >
      {choices.map((choice) => (
        <option key={choice.key} value={choice.key}>
          {choice.default ? `${choice.label} (default)` : choice.label}
        </option>
      ))}
    </select>
  )
}
