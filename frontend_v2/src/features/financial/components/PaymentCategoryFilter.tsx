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
