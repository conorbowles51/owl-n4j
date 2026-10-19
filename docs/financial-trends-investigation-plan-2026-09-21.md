# Financial Trends: research, implementation plan and acceptance

## Investigative purpose

Transactions answers “show me the records and let me filter/chart them”. Follow Money examines connections and payment sequences. Trends must answer “what changed, what accounts for the change, and which records should I inspect next?” Each observation must include its comparison period, exact amounts, supporting transaction IDs, data limitations and a route to a source-linked finding.

The current Trends page repeats monthly/category charts already restored in Transactions. A single populated month repeats totals; missing imported months resemble inactivity; a larger bar provides no attribution. Alex's ARRENDO example also exposes a useful distinction: returned transfers increase gross incoming totals without establishing new income, and a missing name is an information gap rather than a new counterparty.

## Research and interpretation

Primary references reviewed 21 September 2026:

* [FATF, Operational Issues—Financial Investigations Guidance (June 2012)](https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Operational%20Issues_Financial%20investigations%20Guidance.pdf): investigations document origins, beneficiaries and timing, using records to develop evidence. Design implication: observations should lead to the underlying payments and originals, with the investigator recording the explanation. This is guidance, not a prescribed software specification.
* [FFIEC BSA/AML Manual, Appendix F](https://bsaaml.ffiec.gov/manual/Appendices/07): changes in size/frequency, repetitive transfers, rapid onward transfers and limited party information can warrant examination in context. Design implication: compare like-for-like records and make the pattern explicit. We cannot determine inconsistency with a business model from a bank statement alone.
* [FinCEN, Advisory on E-mail Compromise Fraud Schemes (2016)](https://www.fincen.gov/resources/statutes-regulations/guidance/advisory-financial-institutions-e-mail-compromise-fraud): transaction characteristics should be considered with history and circumstances; a single indicator is not a determination of suspiciousness. Design implication: use neutral observations, not risk scores, accusations or automatic findings.

Our chosen comparison windows and recurrence/outlier rules below are product choices, not regulatory thresholds. The feature supports broader financial investigation, not only AML.

## Priority and specification

| Question | Implementation | Evidence and boundaries |
| --- | --- | --- |
| What changed between two periods? | Earlier/later date ranges, quick monthly selection; exact credit/debit totals, counts and differences. | Same currency and bank/card type; accounts explicitly scoped; dates displayed; unequal lengths explained. |
| What drove the difference? | Rank changes by counterparty or category; earlier/later amounts and counts, signed contribution to the total change; open either/both sets. | Unknown names remain an explicit bucket, not an identity. Category and counterparty views are alternative explanations of the same total, not additive. |
| Which names are first seen? | Later-period names absent from earlier loaded records, with first date, volume and count. | Say “first seen in loaded records”, never “new relationship”; no suggestion when no earlier dated history; disclose limits of loaded dates and statement coverage. Suggested names remain marked. |
| Which payments recur? | At least three equal-amount payments to/from the same name in one account, with distinct dates and weekly (5–9 day) or monthly (25–35 day) gaps. | Explain exact rule. Show dates, count and total. Do not infer contract, purpose, duplication or missing expected payments. |
| Which payments depart from earlier amounts? | Later payments exceeding both the earlier maximum and three times the earlier median, with at least five earlier payments in the same account/direction. | Show sample size, median, maximum and multiplier. Neutral “larger than earlier payments”; no anomaly/risk verdict. |
| Are receipts actually returns? | Recognise explicitly described returned SPEI/SPID credits; compare a unique earlier outgoing entry in the same account/currency/amount with the same printed reference within seven days. | Keep both entries and gross totals. Explain reference/amount/date match; do not treat an unknown beneficiary as Banorte merely because the bank is printed. |
| Can this comparison be trusted? | Coverage for each range/account, merging adjoining/overlapping imported statement intervals; flag truncated/unavailable register, incomplete imports, missing dates/amounts/names and unequal windows. | Recorded statement dates do not prove extraction completeness; never infer inactivity from absent records. Suppress percentage claims when coverage is insufficient. |

## Workflow

1. Open Trends; choose account scope and one currency/account type. Start with the largest loaded group and the latest populated month against the preceding month, rather than an arbitrary currency.
2. See data coverage and choose earlier/later dates. Invalid, overlapping or reversed periods cannot produce a comparison.
3. Read concise observations and ranked drivers. An empty section explains what evidence is missing or what rule was not met.
4. Open supporting payments, inspect original statements, then record an observation/question in Findings. Seed the finding with the comparison and limitations; require an investigator to save it.
5. Download a comparison snapshot containing periods, rules, coverage and supporting transaction data. Routine charts remain in Transactions, reached by a clear navigation action.

## People & Businesses profile parity

Profiles reuse the Transactions explorer, including search, account/holder/date/amount/category/proof filters, monthly/category charts, From & To cross-filtering, perspective money flow, table sorting, inline labels, source viewing, selection, findings and downloads. Charts start open. Profile membership is a fixed outer scope: clearing filters never brings in another profile's payments. Filters persist separately for each profile and the main Transactions page. Server-produced exports capture the profile ID and optional currency/type along with active analysis filters; the report's matching row IDs must equal the visible explorer population across all pages. The enclosing export continues to retain its documented wider ledger history for provenance.

Missing-name collections are labelled as payments to investigate, not one person/business. Their profiles get the same explorer and an explicit explanation.

## Counterparty correction carried alongside this work

Inspect the supplied `02 ARRENDO BBVA USD FEB 2021.pdf` pages 1–2. Two P14/CIE entries explicitly label INTERCAM BANCO SA IB (22,000 and 15,000 USD). Add general P14/CIE label recognition, preserving original text and manual edits. The other 11 entries print no counterparty name: two rent transfers, two taxes, one foreign receipt and three outgoing/returned transfer pairs. Follow Money should explain these description groups and expose references instead of presenting all unnamed entries as one entity. Returned transfers receive a descriptive category, without inventing a beneficiary.

## Implementation sequence

1. Finish counterparty recognition and unnamed-payment context, with inference and UI regression tests.
2. Implement pure exact-money comparison/coverage/insight functions and adversarial tests.
3. Replace the old Trends chart page with the investigative workflow; keep source/finding navigation and user scope.
4. Verify browser interactions, responsive layout, failure/empty states and source-linked findings.
5. Replay the actual 672-row finance sunday case, verify financial readings unchanged, push/deploy and check the live workflow.

## Acceptance requirements

* No arithmetic across currencies or card/bank types; no floating-point money totals.
* Invalid or incomplete populations cannot silently produce whole-case claims.
* Partial coverage, unknown dates and unnamed parties are visible beside the analysis.
* Every actionable observation opens exactly its supporting records. Current/prior populations are not mixed accidentally.
* No automatic deletion, reimport, deduplication, ownership assertion, suspicion score or finding submission.
* Existing manual labels take priority over revised suggestions; original financial values remain unchanged.
* Ordinary charts exist in Transactions; Trends is a comparison workflow with explanations and evidence.
* Profiles have the same explorer, with independent saved filters and server-checked export membership.

## Local validation completed

The actual finance sunday replay retains 672 transactions. The ARRENDO USD statement has 17 payments: two newly recognised INTERCAM payee labels total 37,000 USD; three reference-matched outgoing/returned pairs total 39,150 USD on each side; 11 entries have no printed counterparty name. The card comparison for August/September 2021 uses 17 and 11 dated payments and produces four supported observations. No statements or payments were reimported or modified to obtain these results.

Unit and Chromium workflow tests cover exact arithmetic, currency/type separation, missing and overlapping coverage, unknown dates, sparse history, ambiguous returns, evidence IDs, finding drafts, profile chart filtering, source opening, independent profile filters and export boundaries. Live deployment verification follows the release build.
