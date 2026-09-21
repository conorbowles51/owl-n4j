import { useState } from "react"
import { Button } from "@/components/ui/button"

export function AccountMultiSelect({
  label,
  allLabel,
  options,
  selected,
  onChange,
}: {
  label: string
  allLabel: string
  options: { value: string; label: string }[]
  selected: string[]
  onChange: (values: string[]) => void
}) {
  const [search, setSearch] = useState("")
  const labels = new Map(options.map((option) => [option.value, option.label]))
  const visible = options.filter((option) =>
    option.label.toLowerCase().includes(search.toLowerCase())
  )
  return (
    <div className="min-w-56 flex-1 text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      <details
        className="rounded border bg-background"
        aria-label={`${label} filter`}
      >
        <summary className="cursor-pointer p-2">
          {selected.length
            ? `${selected.length} selected · ${selected.map((value) => labels.get(value) || value).join(", ")}`
            : allLabel}
        </summary>
        <div className="space-y-2 border-t p-2">
          <input
            aria-label={`Search ${label.toLowerCase()}`}
            placeholder="Search names or numbers"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded border bg-background p-2"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onChange([])}
            >
              {allLabel}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!visible.length}
              onClick={() =>
                onChange([
                  ...new Set([
                    ...selected,
                    ...visible.map((option) => option.value),
                  ]),
                ])
              }
            >
              Select visible
            </Button>
          </div>
          <div
            className="max-h-52 overflow-y-auto"
            role="group"
            aria-label={`Choose ${label.toLowerCase()}`}
          >
            {visible.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-start gap-2 rounded p-2 hover:bg-muted"
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={selected.includes(option.value)}
                  onChange={(event) =>
                    onChange(
                      event.target.checked
                        ? [...selected, option.value]
                        : selected.filter((value) => value !== option.value)
                    )
                  }
                />
                {option.label}
              </label>
            ))}
            {!visible.length && (
              <p className="p-2 text-muted-foreground">No matching options.</p>
            )}
          </div>
        </div>
      </details>
      {!!selected.length && (
        <div className="mt-1 flex flex-wrap gap-1">
          {selected.map((value) => (
            <button
              type="button"
              key={value}
              className="rounded border bg-muted px-2 py-1 text-xs"
              aria-label={`Remove ${labels.get(value) || value} from ${label.toLowerCase()} filter`}
              onClick={() =>
                onChange(selected.filter((item) => item !== value))
              }
            >
              {labels.get(value) || value} ×
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
