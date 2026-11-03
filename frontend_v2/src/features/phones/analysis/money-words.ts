export type AmountReading = {
  amount_minor?: number | null
  currency?: string | null
  amount_text?: string | null
}

/** "USD 1,234.56" from integer minor units and the currency's exponent; the text as written when either is unknown. */
export function amountWords(m: AmountReading): string {
  if (m.amount_minor == null || !m.currency) return `${m.amount_text} (as written)`
  let exp = 2
  try {
    exp = new Intl.NumberFormat("en-US", { style: "currency", currency: m.currency }).resolvedOptions().maximumFractionDigits ?? 2
  } catch {
    return `${m.amount_text} (as written)`
  }
  const digits = String(m.amount_minor).padStart(exp + 1, "0")
  const whole = digits.slice(0, digits.length - exp).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return `${m.currency} ${whole}${exp ? "." + digits.slice(-exp) : ""}`
}
