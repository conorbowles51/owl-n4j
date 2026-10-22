import {
  usePaymentCategories,
  usePaymentCategory,
} from "../hooks/use-payment-categories"

export function PaymentCategoryFilter({ caseId }: { caseId: string }) {
  const [category, setCategory] = usePaymentCategory(caseId)
  const options = usePaymentCategories(caseId)
  return (
    <label className="flex items-center gap-2 text-sm">
      Category
      <select
        aria-label="Filter financial payments by category"
        className="rounded border bg-background p-2 max-w-56"
        value={category}
        onChange={(event) => setCategory(event.target.value)}
      >
        <option value="">All categories</option>
        {[
          ...new Set([
            "Uncategorized",
            ...(options.data ?? []),
            ...(category ? [category] : []),
          ]),
        ].map((name) => (
          <option key={name}>{name}</option>
        ))}
      </select>
      {options.isError && <span role="alert">Category list unavailable</span>}
    </label>
  )
}

/**
 * Outside Transactions: only says which category narrows the payments shown,
 * with a way back to Transactions (where categories are chosen) or to clear
 * it. Nothing when no category is chosen.
 */
export function ActiveCategoryNotice({
  caseId,
  onChange,
}: {
  caseId: string
  onChange: () => void
}) {
  const [category, setCategory] = usePaymentCategory(caseId)
  if (!category) return null
  return (
    <p role="status" aria-label="Category filter" className="flex items-center gap-2 text-sm">
      <span>
        Showing category: <strong>{category}</strong>
      </span>
      <button type="button" className="underline underline-offset-2" onClick={onChange}>
        Change under Transactions
      </button>
      <button type="button" className="underline underline-offset-2" onClick={() => setCategory("")}>
        Show all categories
      </button>
    </p>
  )
}
