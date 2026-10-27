import { useState } from "react"
import { Tags, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  categoryName,
  usePaymentCategory,
} from "../hooks/use-payment-categories"
import { useCategoryColors } from "../hooks/use-payment-category-library"

const SHOWN = 12

/**
 * Pick one or many categories as chips, each with how many payments it holds
 * under the other filters. Empty selection means every category.
 */
export function PaymentCategoryFilter({
  caseId,
  rows,
  value,
  onChange,
  onManage,
}: {
  caseId: string
  /** Payments matching every filter except category: the counts come from these. */
  rows: { category?: string }[]
  value?: string[]
  onChange?: (next: string[]) => void
  onManage?: () => void
}) {
  const [shared, setShared] = usePaymentCategory(caseId)
  const selected = value ?? shared
  const setSelected = onChange ?? setShared
  const colors = useCategoryColors(caseId)
  const [more, setMore] = useState(false)
  const counts = new Map<string, number>()
  for (const row of rows) {
    const name = categoryName(row)
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  for (const name of selected) if (!counts.has(name)) counts.set(name, 0)
  const ranked = [...counts].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0])
  )
  const visible = more
    ? ranked
    : ranked.filter(
        ([name], index) => index < SHOWN || selected.includes(name)
      )
  const toggle = (name: string) =>
    setSelected(
      selected.includes(name)
        ? selected.filter((n) => n !== name)
        : [...selected, name]
    )
  return (
    <div
      role="group"
      aria-label="Filter by category"
      className="flex flex-wrap items-center gap-1.5 rounded-lg border bg-card p-2"
    >
      <span className="mr-1 inline-flex items-center gap-1.5 text-sm font-semibold">
        <Tags className="size-4 text-primary" aria-hidden="true" />
        Categories
      </span>
      <CategoryChip
        name="All"
        count={rows.length}
        pressed={!selected.length}
        onClick={() => setSelected([])}
      />
      {visible.map(([name, count]) => (
        <CategoryChip
          key={name}
          name={name}
          count={count}
          color={
            name === "Uncategorized"
              ? undefined
              : colors.get(name.toLowerCase())
          }
          pressed={selected.includes(name)}
          onClick={() => toggle(name)}
        />
      ))}
      {ranked.length > visible.length && (
        <Button size="sm" variant="ghost" onClick={() => setMore(true)}>
          +{ranked.length - visible.length} more
        </Button>
      )}
      {more && ranked.length > SHOWN && (
        <Button size="sm" variant="ghost" onClick={() => setMore(false)}>
          Fewer
        </Button>
      )}
      {selected.length > 0 && (
        <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
          <X className="size-3.5" aria-hidden="true" />
          Clear categories
        </Button>
      )}
      {onManage && (
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          onClick={onManage}
        >
          New or manage categories
        </Button>
      )}
    </div>
  )
}

function CategoryChip({
  name,
  count,
  color,
  pressed,
  onClick,
}: {
  name: string
  count: number
  color?: string
  pressed: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={`${name}, ${count.toLocaleString()} payments`}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
        pressed
          ? "border-primary bg-primary text-primary-foreground"
          : "bg-background hover:bg-muted"
      }`}
    >
      {color && (
        <span
          aria-hidden="true"
          className="size-2.5 rounded-full"
          style={{ backgroundColor: color }}
        />
      )}
      {name}
      <span className={pressed ? "opacity-80" : "text-muted-foreground"}>
        {count.toLocaleString()}
      </span>
    </button>
  )
}

/**
 * Outside Transactions: only says which categories narrow the payments shown,
 * with a way back to Transactions (where categories are chosen) or to clear
 * them. Nothing when no category is chosen.
 */
export function ActiveCategoryNotice({
  caseId,
  onChange,
}: {
  caseId: string
  onChange: () => void
}) {
  const [categories, setCategories] = usePaymentCategory(caseId)
  if (!categories.length) return null
  return (
    <p role="status" aria-label="Category filter" className="flex flex-wrap items-center gap-2 border-b bg-[#e8effd] px-4 py-1.5 text-sm text-[#1d4aa6] dark:bg-[#1d2a44] dark:text-[#cfe0ff]">
      <span>
        Showing {categories.length === 1 ? "category" : "categories"}:{" "}
        <strong>{categories.join(", ")}</strong>
      </span>
      <button type="button" className="underline underline-offset-2" onClick={onChange}>
        Change under Transactions
      </button>
      <button type="button" className="underline underline-offset-2" onClick={() => setCategories([])}>
        Show all categories
      </button>
    </p>
  )
}
