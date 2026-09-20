import { supportedCurrencies } from "../lib/currency-catalog"

const names = new Intl.DisplayNames(["en"], { type: "currency" })

/** One supported currency list for batch, statement and saved-record editors. */
export function CurrencyOptions() {
  return <>{supportedCurrencies.map((code) => (
    <option key={code} value={code}>{code} — {names.of(code) || code}</option>
  ))}</>
}
