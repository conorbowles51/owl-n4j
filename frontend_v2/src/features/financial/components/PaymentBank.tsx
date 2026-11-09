/** The bank of the account the payment went through, labelled, on every payment line (never cut off). */
export function PaymentBank({ institution, className = "" }: { institution?: string | null; className?: string }) {
  if (!institution) return null
  return (
    <span className={`flex flex-wrap items-baseline gap-x-1.5 break-words text-[13px] text-muted-foreground ${className}`} data-testid="payment-bank">
      <span className="text-[12px] font-semibold uppercase tracking-wide">Bank</span>
      <span>{institution}</span>
    </span>
  )
}
