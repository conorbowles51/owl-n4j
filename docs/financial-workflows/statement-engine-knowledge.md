# Statement engine knowledge file (harvested from the family readers)

Written by r2-any-layout, 2026-10-06. Code facts only: no real names, numbers or amounts.
Source of every entry: the family readers in `backend/services/financial/statement_import_<family>.py`
(andrews, bbva, card + card_balances + statement_layout_context [Capital One], citi, credit_one, kapital
[Kapital and Intercam], merrick, monex, santander, scotiabank), the shared `statement_import_proposal.py`,
`statement_import_controls.py`, `statement_printed_no_activity.py`, `review_arithmetic.py`,
`statement_admission.py`, and the WIP notes of c-generic, c-mx-layouts, c-mx-noactivity, r1-monex-citi,
r1-reproduced.

This list is the general engine's feature list and its test list. Each rule has:
**problem** (what a reader solves), **general rule** (the institution-free form the engine uses), **families**
(which readers need it; the count is the justification required by the engine rules: a rule enters engine code
only with at least two families or a format convention not tied to one institution), and **engine** (covered /
partial / library: where the engine implements it, or why it stays in the fallback library).

Family abbreviations: AND andrews, BBVA bbva, C1 capital-one (card + card_balances + layout_context),
CITI citi, CR1 credit_one, KAP kapital/intercam, MER merrick, MON monex, SAN santander, SCO scotiabank.

## A. Identity and grouping

| # | Problem | General rule | Families | Engine |
|---|---|---|---|---|
| A1 | Several statements (cycles) in one PDF | A statement is keyed by its printed period (and account when printed); pages printing a different period start another statement | C1, CITI, CR1, MER, AND, BBVA (one per sequence), SAN, KAP (11 / 10 families) | covered (`_segments`) |
| A2 | Continuation pages do not repeat the period | A page without its own period continues the previous page's statement only when nothing on it contradicts (no other period) | C1, BBVA, SAN, MON, AND, CITI (6) | covered |
| A3 | Missing pages | Printed page numbering ("Página n de m", "Page n of m", "Hoja n de m", "n / m") must be complete for the run; a gap refuses the period | BBVA, MON, CITI, AND, SAN, KAP, C1 (7) | covered (`page_numbering`) |
| A4 | Reprint of the same statement inside a file | A second run that restarts at page 1 with the same identity is a separate printing; compared, never merged | C1, AND (2) | partial: a restart at "page 1" starts a new segment; equal segments are left to the existing duplicate set-aside |
| A5 | Blank numbered pages | A page printed only with its number between two correctly numbered pages is part of the run | MON (1) + format convention (page numbering) | covered (numbering counts the page; no rows needed) |
| A6 | Account reference | Labelled value: "No. de cuenta", "Número de cuenta", "Cuenta", "Contrato", "Account number", "Account ending in", masked "****1234"; label value in the next cell, the same cell after the label, or a vertically merged label column zipped with its values | BBVA, MON, SAN, KAP, C1, CITI, CR1, MER, AND (9) | covered (labels table) |
| A7 | Several accounts or currency sections in one statement | A section is bounded by its own controls; each section is its own period | MON, KAP, SAN, AND (4) | partial: segments are split at each new opening-balance control that follows a closing one on a later row; per-section accounts not read separately (held when ambiguous) |
| A8 | Holder | Top line of the address block that ends with a postal-code line, or a labelled name ("Nombre del Receptor", "Titular", "Account Name") | BBVA, MON, CR1, MER, AND, SAN, KAP, SCO, CITI (9) | covered (label, then address block); absent -> left empty (grouped decision) |
| A9 | Institution | Legal-name furniture line repeated on the statement's pages ("Banco ..., S.A.", "... Bank, N.A.", "Institución de Banca Múltiple", "Credit Union") | all 10 | covered (repeated legal-name line); absent -> empty (grouped decision) |
| A10 | Counterparty bank names in descriptions are not the issuer | Issuer identity only from furniture/legal-name lines, never from movement descriptions | KAP, BBVA, SAN (3) | covered (movement rows excluded from institution search) |
| A11 | Information pages (rewards, fee summaries, legal text, tax certificates) | Pages without controls or movements contribute nothing and do not break a run | C1, AND, MER, BBVA, KAP, MON (6) | covered (no rows taken) |
| A12 | Investment / non-cash statements (units x price) | Not a cash account: no proof is possible, never admitted | observed in real unread set; format convention | covered by fail-closed proof (held, named reason) |

## B. Period and dates

| # | Problem | General rule | Families | Engine |
|---|---|---|---|---|
| B1 | Printed period formats | Two full dates joined by a range word: "DEL d AL d", "d AL d", "d - d", "d to d", "d through d"; dates as dd/mm/yyyy, dd-MMM-yyyy, d MMMM yyyy, MM/DD/YY (US), Month d, yyyy | BBVA, SAN, MON, KAP, C1, CITI, CR1, MER, AND (9) | covered |
| B2 | Row dates without a year | dd/MMM, dd-MMM, MM/DD, "dd MMM": the year comes from the period; exactly one candidate inside the period (or the allowed window) | BBVA, MON, KAP, C1, CITI, CR1, MER, AND (8) | covered |
| B3 | Day/month order | US layouts print month first, Mexican/European day first; the order is fixed per document by unambiguous dates (day > 12) and by the printed period's own format; still ambiguous -> hold | CITI, C1, CR1, MER (month first) vs BBVA, SAN, KAP, MON (day first) (8) | covered |
| B4 | Rows dated before the cycle | A card purchase may be dated up to 31 days before the cycle start when its posting date is inside it | C1, CITI, AND (3) | covered (window: period start - 31 days, liability convention only) |
| B5 | Posting vs transaction date | Two dates on one line: the first printed date is the row date, the second is kept as a secondary date | C1, CITI, BBVA (oper/liq), MON (pactada), AND, CR1 (6) | covered (second date kept as `value_date`) |
| B6 | Interest/fee lines without a date | A charge line without a date in the card convention is ordered at the period end and never given a printed date (`date_basis=statement_end_ordering_only`) | C1, CITI (2) | covered (liability convention only) |
| B7 | Quiet cycles proved by printed zeros | All printed movement totals zero and equal opening/closing -> source proof of no activity | CITI, MON, SAN, KAP, SCO, AND (6) | covered (`no_activity_evidence` via `statement_printed_no_activity.zero_totals_evidence`) |

## C. Amounts and signs

| # | Problem | General rule | Families | Engine |
|---|---|---|---|---|
| C1 | Grouping/decimal separators | 1,234.56 (US/MX) or 1.234,56 (EU); decided per document from unambiguous tokens; mixed evidence -> hold | SAN, KAP (mixed-separator documents), all others dot-decimal (10) | covered |
| C2 | Currency markers | Leading `$`/code or trailing code ("MN", "MXN", "USD") stripped only when consistent with the statement currency | KAP (MN), MON, C1, CITI, SAN, CR1 (6) | covered |
| C3 | Whole-unit currencies | Yen has no minor unit: amounts without decimals are valid only when the currency exponent is 0 | MON (1) + ISO 4217 convention | covered (exponent from `money.get_currency`) |
| C4 | Trailing minus / CR / parentheses | A trailing `-`, `CR` or `( )` marks a negative/credit value; a detached minus cell belongs to the amount on its right | CR1, MER, C1, AND, SAN, BBVA, SCO (7) | covered (signed tokens) |
| C5 | Card sign convention (amounts owed) | Balances are amounts owed: charges raise them, payments lower them; a signed amount's sign gives direction; equation open + debits - credits = close | C1, CITI, CR1, MER (4) | covered (liability convention tried by proof; chosen only with printed card-vocabulary evidence or a unique proof) |
| C6 | Split debit/credit columns | Two amount columns; the column gives direction, amount positive | BBVA, SAN, KAP, MON, AND, SCO (6) | covered |
| C7 | Signed single amount column | One amount column; sign gives direction | C1, CITI, CR1, MER (4) | covered |
| C8 | Running balance column(s) | Zero, one or several balance columns (operation vs settlement, available vs total); one must chain | BBVA (2 columns), MON (3), SAN, KAP, AND (5) | covered (each candidate balance column tried) |
| C9 | Balance printed only on some rows (end of day) | Rows without a balance accumulate into the next printed balance | BBVA, SAN, AND (3) | covered (shared `review_arithmetic` interval logic) |
| C10 | Merged cells (several values in one cell) | A cell holding several amounts/date+text is split into tokens; positions estimated by character offset; exact-cell positions win | MON, CITI, BBVA, SAN, AND, C1, MER, SCO (8) | covered (tokeniser) |
| C11 | Digits split by OCR spaces | Only inside a single measured money cell, and only when the result is one well-formed amount | AND (1) | library (one family) |
| C12 | Lines with no credit or debit (net-zero interest) | A movement line without money in an amount column is not a payment | MON (1) | covered as a consequence of C6 (no amount -> not a movement) |

## D. Controls (what proves a period)

| # | Problem | General rule | Families | Engine |
|---|---|---|---|---|
| D1 | Opening balance labels | saldo anterior / inicial / saldo final del periodo anterior / saldo de operación|liquidación inicial / previous / opening / beginning balance / balance forward | all 10 | covered (labels table) |
| D2 | Closing balance labels | saldo final / saldo al corte / saldo de operación final / saldo vista / new / closing / ending balance | all 10 | covered |
| D3 | Two balance bases printed (operation vs settlement) | Several candidate opening/closing values: the one that proves wins; two different proving readings -> hold | BBVA, MON (2) | covered (control candidates searched with the column roles) |
| D4 | Credit / debit totals with counts | "Depósitos / Abonos (+) n amount", "Retiros / Cargos (-)", "Total abonos", "Total deposits/withdrawals", "Payments", "Purchases": printed totals and counts must equal what was read | BBVA, MON, SAN, KAP, CITI, C1, MER, SCO (8) | covered |
| D5 | Page subtotals / carried-forward lines | A subtotal or "carried forward"/"brought forward" line is a control, never a payment | AND, CR1, CITI, C1 (4) | covered (control labels never become movements) |
| D6 | Table endpoints repeat the summary | "Saldo inicial:"/"Saldo final:" lines bounding the movement table must equal the summary | MON, SAN (2) | covered (equal values merge; unequal values -> both candidates, proof decides, two proofs -> hold) |
| D7 | Summary components (fees, interest, purchases) | Every printed component must equal what was read | CITI, MER, C1 (3) | partial: total labels for credit/debit are compared; fee/interest components are not yet modelled (library) |
| D8 | Fail-closed proof | opening + credits - debits = closing to the cent AND (running chain holds on every printed balance OR every printed total/count matches) | all families' admission gate (`statement_admission`) | covered (`_prove`) |

## E. Movement table structure

| # | Problem | General rule | Families | Engine |
|---|---|---|---|---|
| E1 | Header recognition | A header line holds a date word and at least one money word (Spanish and English vocabulary); it fixes column bands | all 10 | covered (labels table; header is a hint, proof decides) |
| E2 | Column bands from geometry | Money tokens are assigned to columns by right-edge alignment (amounts are right aligned) | BBVA, SAN, KAP, MON, CITI, MER, AND (7) | covered |
| E3 | Multi-line descriptions | Lines with no date and no money below a movement continue its description | BBVA, SAN, KAP, MON, CITI, CR1, AND, C1 (8) | covered |
| E4 | Two-line entries (amount on the next line) | A dated line without money followed by an undated line with money is one movement | CITI (1) | library |
| E5 | Descriptions wrapping above the dated line | Wrapped lines are owned by the nearest dated line | MON (1) | library |
| E6 | Table furniture inside the table region | Page headers/footers, "page n of m" and legal lines inside a movement region are ignored | BBVA, MON, SAN, C1 (4) | covered (furniture = text repeated on most pages) |
| E7 | Prior-period settlement blocks | Movements of earlier periods repeated to explain a settlement balance are not this period's payments | BBVA (1) | library |
| E8 | Rewards / notices column beside the table | Only the transaction column band is read | CITI, C1 (2) | partial: tokens left of the date band or right of the last money band are ignored |
| E9 | Movement region bounds | Region starts after a header and ends at a total/closing line or a terminator heading | BBVA, SAN, MON, KAP (4) | covered |

## F. Image and text-layer conditions

| # | Problem | General rule | Families | Engine |
|---|---|---|---|---|
| F1 | OCR glyph substitutions in labels | Labels match after accent folding; only a documented set of glyph confusions in fixed labels | BBVA, AND, C1 (3) | covered (accent/case folding only; no glyph repair of values) |
| F2 | Invisible producer OCR layers | Treated as recognised text so crop checks apply | all image families (pipeline rule, r1-reproduced) | inherited (engine reads the same sources) |
| F3 | Vector-outline text (no text layer) | Pages must go to image reading | real unread set (inventory `vector_text`) | see "Vector text" below |

## Counts

- Rules: **47** (A 12, B 7, C 12, D 8, E 9, F 3 — counting F2/F3 as pipeline rules).
- Engine covers fully: **38**; partially: **4** (A4, A7, D7, E8); library only: **5** (C11, E4, E5, E7 and
  the institution-specific label vocabularies that cannot be expressed in the shared table).
- Rules justified by one family only and kept in the library: C11, E4, E5, E7. One-family rules that the engine
  covers are covered as consequences of a format convention (A5 page numbering, C3 ISO exponent, C12 split columns).

## Vector text

Inventory mode `vector_text` = the page has drawn glyph outlines and no extractable text layer. See WIP-NOTES for
the pipeline routing finding and counts.
