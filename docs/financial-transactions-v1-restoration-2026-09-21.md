# Transactions: restore the connected investigation workflow

## Evidence and diagnosis

Reviewed Neil's six 21 September screenshots and the v1 FinancialView, MoneyFlowSection and EntityFlowTables implementation at ed3eef75. The successful interaction is a single analytical workspace: change a selection and inspect its effect on amounts, counterparties, charts and source-linked transactions without changing tabs.

1. **10.50.17:** searchable, sortable From and To lists with independent multiple selections, removable chips, reciprocal counts/amounts, and a visible intersection of filters. Loupe currently sends name clicks to a separate People page.
2. **10.50.38:** a selected group of names defines incoming, outgoing, net and internal activity. External counterparties have a divergent bar chart. The selected group is independent of From/To filtering; both apply together.
3. **10.50.57:** adding names changes the perspective immediately. Selection is a set, not a single account. Internal rows have both endpoints selected and stay outside external-flow bars.
4. **10.51.09:** compact sortable rows keep names, direction, category, source reference and notes near the transaction. Selection, editing, pagination and source inspection belong to that same workspace.
5. **10.51.25:** all analysis sections can collapse while the totals and table remain useful. Collapsing a section must not silently remove its filters.
6. **10.51.37:** a time chart and category distribution reveal patterns before opening rows. They operate on the same active population and must lead back to the supporting transactions.

The current shared PaymentTotals has three unlabelled groups in finance sunday. Its grouping logic separates USD card postings, USD bank payments and EUR bank payments, but the presentation makes the distinction depend on interpreting individual tiles. The v1-like components retained in Loupe use the other-record data model; importing them unchanged would omit statement-ledger rows and lose exact monetary arithmetic.

## Implementation contract

- Transactions opens with all imported rows. Account/holder, dates, search, currencies, categories, From, To and perspective filters are visible and removable. Selections persist when a panel is collapsed or a source is opened.
- Restore collapsible Charts, From & To and Money flow inside the imported-transactions workspace. Keep the existing corrections, findings, source citations and evidence history.
- From/To selections are OR within a side and AND between sides. Each list is constrained by the opposite side and perspective, not its own selection; selected zero-match entries remain removable.
- Perspective selects displayed names. A row touching any selected name is included; both endpoints selected means internal, otherwise incoming or outgoing relative to the selection. Name grouping does not establish an identity or reconcile duplicate bank postings. Each ledger entry contributes once; unpaired mirrored bank entries are not silently deduplicated.
- Currency and bank/card account type remain separate in totals, rankings and charts. Use exact integer minor units; no implicit dollar currency or float summation. Clearly label all summary groups throughout Financial. Net account activity is distinguished from account balances and from selected-name perspective flow.
- Time/category/flow drill-downs filter the table and exports and have an explicit clear action. Undated entries remain accessible and are not assigned an invented chart date. No ten-row analytical truncation; all rows contribute, with pagination for long lists.
- A compact table exposes sortable Date, Description, From, To, Category and amount columns, immediate name/category editing, row references and optional expanded details. Original values and suggested-label origins remain visible.
- Verify realistic multi-currency/card data, multiple selections and intersections, clearing/collapsing, internal/external arithmetic, large values, all-page export consistency, responsive layout and the actual live finance sunday case.

## Deliberate distinctions from the screenshots

The screenshots contain some names that look like extracted balance fragments. Those are not a model for identity inference. Reuse the interaction, keep provenance and the current editable suggestion layer. Likewise, v1's USD-only floating-point amounts and technical Legacy/Audit data toggles are not appropriate for authoritative imported statement totals. Every total and chart must identify the data it includes in ordinary language.

## Validation and scope

- Restored Notes CSV with a reference-matching preview, quoted/multiline CSV parsing, ambiguous-reference exclusion, source-linked notes and retry recognition; existing labels and financial readings are preserved.
- Added CSV download for the complete filtered list and server capture of From/To, perspective, chart and sort filters. Large selections use a POST body and a filter digest, avoiding URL/header length limits.
- 38 frontend unit tests, 63 backend tests and two Chromium workflow tests passed, including the existing source/comparison/finding journey. Production build and scoped lint checked.
- Read-only local replay of the actual finance sunday ledger: all 672 rows retained (653 USD card, 17 USD bank, 2 EUR bank). Six frontend/server filter combinations matched exact transaction IDs: 672, 564, 667, 312, 328 and 17 results. A 29,568-row replay of filtering and party aggregation completed in approximately 66 ms on this Mac; this measures calculation time, not network or whole-page load time.
- Private case data and replay outputs stay under ignored local-runtime storage. Browser acceptance screenshots use synthetic transactions.
