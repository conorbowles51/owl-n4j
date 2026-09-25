import { bankKey } from "../lib/account-selection"
import type { PaymentProfile } from "../lib/investigator-workspace"

export function ProfileStatementSummary({
  profile,
}: {
  profile: PaymentProfile
}) {
  const accounts = profile.accountDetails
  const banks = [
    ...new Map(
      accounts.flatMap((account) =>
        account.institution?.trim()
          ? [[bankKey(account.institution), account.institution] as const]
          : []
      )
    ).values(),
  ]
  const currencies = [
    ...new Set(
      accounts.flatMap((account) =>
        account.currency ? [account.currency] : []
      )
    ),
  ].sort()
  const references = accounts.filter((account) => !account.registered).length
  const unknownBanks = accounts.filter(
    (account) => !account.institution?.trim()
  ).length
  const unknownNumbers = accounts.filter(
    (account) => !account.number?.trim()
  ).length
  const unknownCurrencies = accounts.filter(
    (account) => !account.currency
  ).length
  const unknownTypes = accounts.filter((account) => !account.accountType).length
  const missingDates = profile.statementPeriods.filter(
    (period) => !period.start || !period.end
  ).length
  const coverageUnavailable = accounts.some(
    (account) => account.statementPeriods === undefined
  )
  return (
    <div
      role="group"
      aria-label="Saved account and statement records"
      className="space-y-1 text-xs text-muted-foreground"
    >
      <p>
        {accounts.length} {accounts.length === 1 ? "account" : "accounts"} ·{" "}
        {banks.length
          ? `${banks.length} ${banks.length === 1 ? "bank" : "banks"}`
          : "Bank not recorded"}{" "}
        ·{" "}
        {coverageUnavailable && !profile.sources.length
          ? "Source count unavailable"
          : `${profile.sources.length} ${coverageUnavailable ? "known " : ""}source ${profile.sources.length === 1 ? "document" : "documents"}`}
      </p>
      <p>
        Banks recorded: {banks.join(", ") || "Not recorded"}. Currencies
        recorded: {currencies.join(", ") || "Not recorded"}.
      </p>
      {(unknownBanks > 0 ||
        unknownNumbers > 0 ||
        unknownCurrencies > 0 ||
        unknownTypes > 0) && (
        <p>
          Details not recorded:{" "}
          {[
            unknownBanks &&
              `${unknownBanks} bank ${unknownBanks === 1 ? "name" : "names"}`,
            unknownNumbers &&
              `${unknownNumbers} account ${unknownNumbers === 1 ? "number" : "numbers"}`,
            unknownCurrencies &&
              `${unknownCurrencies} ${unknownCurrencies === 1 ? "currency" : "currencies"}`,
            unknownTypes &&
              `${unknownTypes} account ${unknownTypes === 1 ? "type" : "types"}`,
          ]
            .filter(Boolean)
            .join(" · ")}
          .
        </p>
      )}
      {references > 0 && (
        <p>
          {references} account{" "}
          {references === 1 ? "reference has" : "references have"} no matching
          registered account details. A reference is not confirmation of account
          ownership.
        </p>
      )}
      {profile.statementPeriods.length > 0 ? (
        <p>
          Saved statement dates:{" "}
          {profile.statementFirst || "Start not recorded"} to{" "}
          {profile.statementLast || "end not recorded"} ·{" "}
          {profile.statementPeriods.length} saved{" "}
          {profile.statementPeriods.length === 1 ? "period" : "periods"}.
          {missingDates > 0
            ? ` ${missingDates} periods have incomplete dates.`
            : ""}
          {profile.statementPeriods.length > 1
            ? " This span may contain gaps."
            : ""}
        </p>
      ) : (
        <p>
          {coverageUnavailable
            ? "Saved statement dates are unavailable in this directory."
            : "No saved statement periods linked to these accounts."}
        </p>
      )}
      {profile.statementPeriods.length > 0 && coverageUnavailable && (
        <p>Statement coverage is unavailable for some account references.</p>
      )}
      {profile.kind === "owner" && profile.statementPeriods.length > 0 && (
        <p>
          These are account statement dates, not the dates of this person’s
          ownership or payments.
        </p>
      )}
    </div>
  )
}
