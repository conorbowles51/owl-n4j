import {
  usePaymentCategoryLibrary,
  useCreatePaymentCategory,
} from "../hooks/use-payment-category-library"
import { CategoryManagementDialog } from "./CategoryManagementDialog"

export function PaymentCategoryManager({
  caseId,
  onClose,
}: {
  caseId: string
  onClose: () => void
}) {
  const categories = usePaymentCategoryLibrary(caseId)
  const create = useCreatePaymentCategory(caseId)
  return (
    <CategoryManagementDialog
      caseId={caseId}
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      categories={categories.data ?? []}
      onCreateCategory={create}
      sharedPayments
      loading={categories.isPending}
      loadError={categories.isError ? categories.error.message : undefined}
      onReload={() => void categories.refetch()}
    />
  )
}
