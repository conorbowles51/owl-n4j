import { ClaimComparisonDecision } from "./ClaimComparisonDecision"
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { verifyClaimComparison } from "../lib/claim-comparison"
import { LedgerFilters } from "./LedgerFilters"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { ClaimEvidencePicker } from "./ClaimEvidencePicker"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"
export function PaymentClaimComparison({ caseId }: { caseId: string }) {
  const [account, setAccount] = useState<string | undefined>()
  return (
    <section aria-label="Payment claim comparison" className="space-y-4 p-4">
      <h2 className="font-semibold">
        Compare a payment claim with the records
      </h2>
      <p>
        Copy the original words and preserve any uncertainty as amount and date
        ranges. The account holder and interpretation are explicit assumptions.
        This comparison never adds a claim to ledger totals.
      </p>
      <LedgerFilters
        caseId={caseId}
        accountOnly
        onApply={(p) => setAccount(p.accountId)}
      />
      {account ? (
        <ClaimForm key={account} caseId={caseId} accountId={account} />
      ) : (
        <p>Select one account to compare the claim.</p>
      )}
    </section>
  )
}
function ClaimForm({
  caseId,
  accountId,
}: {
  caseId: string
  accountId: string
}) {
  const [source, setSource] = useState<{ id: string; label: string } | null>(
      null
    ),
    [opened, setOpened] = useState<string | null>(null),
    [page, setPage] = useState(0)
  const [fields, setFields] = useState({
    quote: "",
    source_location: "",
    speaker: "",
    payer: "",
    payee: "",
    currency: "GBP",
    low: "",
    high: "",
    earliest: "",
    latest: "",
    account_holder: "",
    interpretation_basis: "",
    percent: "0",
    floor: "0",
    population: "verified",
  })
  const set = (key: keyof typeof fields, value: string) =>
    setFields((v) => ({ ...v, [key]: value }))
  const compare = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!source) throw Error("Select the source of the claim.")
      const low = correctionMinor(fields.low, fields.currency),
        high = correctionMinor(fields.high, fields.currency),
        basisPoints = correctionMinor(fields.percent, "GBP")
      if (
        low === null ||
        high === null ||
        BigInt(low) > BigInt(high) ||
        basisPoints === null ||
        BigInt(basisPoints) > 10000n ||
        !/^\d+$/.test(fields.floor) ||
        Number(fields.floor) > 1000000
      )
        throw Error(
          "Enter valid exact amount bounds and a tolerance from0–100%."
        )
      const request = {
        account_id: accountId,
        source_file_id: source.id,
        quote: fields.quote,
        source_location: fields.source_location,
        speaker: fields.speaker || null,
        payer: fields.payer || null,
        payee: fields.payee || null,
        currency: fields.currency,
        amount_low_minor: low,
        amount_high_minor: high,
        earliest: fields.earliest,
        latest: fields.latest,
        account_holder: fields.account_holder,
        interpretation_basis: fields.interpretation_basis,
        materiality_basis_points: Number(basisPoints),
        materiality_floor_major_units: Number(fields.floor),
        population: fields.population,
      }
      return verifyClaimComparison(
        await fetchAPI(candidateUrl("claim-comparison", caseId), {
          method: "POST",
          body: request,
          timeout: 120000,
        }),
        caseId,
        request
      )
    },
  })
  const download = () => {
    if (!compare.data) return
    const url = URL.createObjectURL(
        new Blob([compare.data.envelope.scenario_json], {
          type: "application/json",
        })
      ),
      a = document.createElement("a")
    a.href = url
    a.download = "loupe-payment-claim-comparison.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const result = compare.data?.value
  return (
    <div className="space-y-4">
      <ClaimEvidencePicker
        caseId={caseId}
        value={source}
        onChange={(v) => {
          setSource(v)
          compare.reset()
        }}
      />
      <form
        onSubmit={(e) => {
          e.preventDefault()
          setPage(0)
          compare.mutate()
        }}
        onChange={() => compare.reset()}
      >
        <fieldset disabled={compare.isPending} className="space-y-3">
          <legend>Claim as stated, and your interpretation</legend>
          <label className="block">
            Original quotation
            <textarea
              aria-label="Original claim quotation"
              required
              maxLength={8192}
              value={fields.quote}
              onChange={(e) => set("quote", e.target.value)}
              className="block w-full border bg-background p-2"
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["source_location", "Source page, paragraph or time"],
                ["speaker", "Speaker (if known)"],
                ["payer", "Payer as named"],
                ["payee", "Payee as named"],
                ["account_holder", "Account holder assumption"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  aria-label={label}
                  required={
                    key === "source_location" || key === "account_holder"
                  }
                  maxLength={512}
                  value={fields[key]}
                  onChange={(e) => set(key, e.target.value)}
                  className="block w-full border bg-background p-2"
                />
              </label>
            ))}
            <label>
              Claim currency
              <input
                aria-label="Claim currency"
                required
                pattern="[A-Z]{3}"
                maxLength={3}
                value={fields.currency}
                onChange={(e) => set("currency", e.target.value.toUpperCase())}
                className="block w-full border bg-background p-2"
              />
            </label>
            {(
              [
                ["low", "Claim amount from"],
                ["high", "Claim amount through"],
                ["percent", "Additional amount tolerance (%)"],
                ["floor", "Minimum tolerance (whole currency units)"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  aria-label={label}
                  required
                  inputMode="decimal"
                  maxLength={32}
                  value={fields[key]}
                  onChange={(e) => set(key, e.target.value)}
                  className="block w-full border bg-background p-2"
                />
              </label>
            ))}
            {(
              [
                ["earliest", "Claim earliest date"],
                ["latest", "Claim latest date"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  aria-label={label}
                  required
                  type="date"
                  min={key === "latest" ? fields.earliest : undefined}
                  value={fields[key]}
                  onChange={(e) => set(key, e.target.value)}
                  className="block w-full border bg-background p-2"
                />
              </label>
            ))}
          </div>
          <label className="block">
            Basis for the ranges and account interpretation
            <textarea
              aria-label="Claim interpretation basis"
              required
              maxLength={4096}
              value={fields.interpretation_basis}
              onChange={(e) => set("interpretation_basis", e.target.value)}
              className="block w-full border bg-background p-2"
            />
          </label>
          <label>
            Comparison population{" "}
            <select
              aria-label="Claim comparison population"
              value={fields.population}
              onChange={(e) => set("population", e.target.value)}
              className="border bg-background p-2"
            >
              <option value="verified">Verified only</option>
              <option value="working">Working readings, including P3</option>
            </select>
          </label>
          <p>
            The added tolerance is the larger of the percentage of the range
            midpoint and the stated minimum. Zero compares the entered range
            exactly.
          </p>
          <Button type="submit" disabled={!source}>
            {compare.isPending
              ? "Comparing…"
              : "Compare claim with captured ledger"}
          </Button>
        </fieldset>
      </form>
      <RequestedCoveragePanel
        caseId={caseId}
        params={{
          accountId,
          startDate: fields.earliest || undefined,
          endDate: fields.latest || undefined,
        }}
      />
      {compare.isError && <p role="alert">{compare.error.message}</p>}
      {result && (
        <section
          aria-label="Payment claim comparison result"
          className="space-y-3"
        >
          <h3 className="font-semibold">
            {result.comparison.outcome === "corroborated"
              ? "Rule proposal: possible corroboration"
              : "Rule proposal: unresolved"}
          </h3>
          <p>
            Claim class P4 · {fields.population} population · allowed amount
            tolerance{" "}
            {correctionMoney(
              result.comparison.tolerance.minor_units,
              result.comparison.tolerance.currency
            )}
          </p>
          {result.limitations.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {result.comparison.notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {result.comparison.unresolved_reason && (
            <p>
              Unresolved reason:{" "}
              {result.comparison.unresolved_reason.replaceAll("_", " ")}
            </p>
          )}
          <p>
            {result.date_unavailable_ids.length} readings have unknown
            transaction timing and were not matched.{" "}
            {result.comparison.candidates.length} dated readings compared.
          </p>
          {result.comparison.candidates
            .slice(page * 20, page * 20 + 20)
            .map((candidate) => (
              <article
                key={candidate.entry.transaction_id}
                className="rounded border p-3"
              >
                <h4 className="font-semibold">
                  {candidate.verdict.replaceAll("_", " ")} ·{" "}
                  {correctionMoney(
                    candidate.entry.amount.minor_units,
                    candidate.entry.amount.currency
                  )}{" "}
                  · {candidate.entry.proof_class.toUpperCase()}
                </h4>
                <p>
                  {candidate.entry.ordering_date} (
                  {candidate.entry.chronology_basis.replaceAll("_", " ")}) ·{" "}
                  {candidate.entry.description}
                </p>
                {Object.values(candidate.components).map((component) => (
                  <p key={component.name}>
                    {component.name.replaceAll("_", " ")}: {component.agreement}{" "}
                    — {component.detail}
                  </p>
                ))}
                <Button
                  variant="outline"
                  onClick={() => setOpened(candidate.entry.transaction_id)}
                >
                  Inspect comparison reading{" "}
                  {candidate.entry.transaction_id.slice(0, 8)}
                </Button>
              </article>
            ))}
          {result.comparison.candidates.length > 20 && (
            <div className="flex gap-2">
              <Button disabled={!page} onClick={() => setPage(page - 1)}>
                Previous comparison readings
              </Button>
              <Button
                disabled={
                  (page + 1) * 20 >= result.comparison.candidates.length
                }
                onClick={() => setPage(page + 1)}
              >
                Next comparison readings
              </Button>
            </div>
          )}
          <ClaimComparisonDecision
            key={compare.data!.envelope.scenario_sha256}
            report={compare.data!}
          />
          <Button onClick={download}>
            Download claim comparison with sources
          </Button>
        </section>
      )}
      {opened && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={opened}
          onClose={() => setOpened(null)}
        />
      )}
    </div>
  )
}
