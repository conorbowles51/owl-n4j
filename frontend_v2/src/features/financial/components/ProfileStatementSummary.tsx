import { bankKey } from "../lib/account-selection"
import type { PaymentProfile } from "../lib/investigator-workspace"
import { statementFacts, type ProfileStatementFacts } from "../lib/people-first-view"

export function ProfileStatementSummary({
  profile,
}: {
  profile: PaymentProfile
}) {
  return <ProfileStatementSummaryView facts={statementFacts(profile)} />
}

/** The summary from its facts: worked out from a profile (ProfileStatementSummary) or answered by the server for
 * the list of names and accounts (GET /ledger-people-view), the same facts either way. */
export function ProfileStatementSummaryView({
  facts: profile,
}: {
  facts: ProfileStatementFacts
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
  const missingDates = profile.statementMissingDates
  const coverageUnavailable = accounts.some((account) => !account.coverage)
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
        {coverageUnavailable && !profile.sources
          ? "Source count unavailable"
          : `${profile.sources} ${coverageUnavailable ? "known " : ""}source ${profile.sources === 1 ? "document" : "documents"}`}
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
      {profile.statementPeriods > 0 ? (
        <p>
          Saved statement dates:{" "}
          {profile.statementFirst || "Start not recorded"} to{" "}
          {profile.statementLast || "end not recorded"} ·{" "}
          {profile.statementPeriods} saved{" "}
          {profile.statementPeriods === 1 ? "period" : "periods"}.
          {missingDates > 0
            ? ` ${missingDates} periods have incomplete dates.`
            : ""}
          {profile.statementPeriods > 1
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
      {profile.statementPeriods > 0 && coverageUnavailable && (
        <p>Statement coverage is unavailable for some account references.</p>
      )}
      {profile.kind === "owner" && profile.statementPeriods > 0 && (
        <p>
          These are account statement dates, not the dates of this person’s
          ownership or payments.
        </p>
      )}
    </div>
  )
}
