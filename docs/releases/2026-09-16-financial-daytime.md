# Financial daytime work, 16 September 2026

The daytime plan removes a remaining restriction on linking payments to people or businesses, fixes demonstrated missed readings in scanned Andrews statements, and prepares a short exercise for the team's evening test.

## Larger payment groups

An investigator can select all matching payments across pages and link them to one person or business. The previous 100-payment selection restriction is removed. The directory supports up to 100,000 retained payment records, including earlier corrections, with a 64 MB complete-response bound and 250,000 payment-link decisions. These are resource bounds, not measured performance guarantees at the maximum.

The server checks the case and current revision, locks selected records in database batches and commits the entire operation together. A missing or changed record refuses the operation. Original descriptions, names and payment values remain unchanged. Complete history capture now supports 250,000 relevant decisions and batches its source IDs, avoiding a second restriction after a larger linking operation. Existing complete-package byte bounds still apply.

If a save response is lost after the server has saved the links, the UI retains the selection and explanation, reloads the records and prevents an automatic retry against the previous revision. Original names within a large linked group are collapsed and shown 25 at a time; all underlying payments remain available.

## Readable text missed because of inserted spaces

Reader version `statement-review-v16` accepts spaces inside digits only where the measured source cells separate a payment amount from its balance. A single measured opening or closing balance can use the same rule. Combined ambiguous amount/balance text stays flagged. The fixed printed words Withdrawal, Deposit and Recurring also accept inserted spaces while preserving their letters and the original description.

The reader does not substitute damaged digits or decimal marks. Conflicting payment signs, unclear dates and missing pages remain flagged. Previously imported payments are not rewritten by this change.

The retained v15 comparison covers 58 Andrews sections. It identifies three newly read payment amounts, nineteen balances and eleven payment directions. All previously populated dates, amounts, balances, directions and descriptions, and every original source cell, are unchanged. Original PDF pages were visually checked for the demonstrated missed amounts and balance. Four revised sections were also checked through the actual local API. No real payments were imported. These checks do not constitute an independent reference measurement of all extraction accuracy.

## Team test exercise

The short checklist is published at `/docs/financial-testing/index.html` and linked from the Financial guide. It opens separately so the investigator keeps the case open. Its downloadable pack contains two explicitly synthetic PDFs and the checklist in HTML and Markdown.

The exercise starts with eight payments in two accounts and gives exact expected counts and totals. It then covers finding a payment, opening its PDF, making an explained description correction, comparing names and transfers, saving findings and downloading a report for a colleague. Real-file checks and useful problem-report details follow.

## Verification

- Backend: 64 focused payment-link, account-party and ledger-snapshot checks passed. A 5,001-payment link/clear/relink sequence retained 15,003 decisions, exact original money and complete grouped analysis. Oversize results and a missing selected record leave no partial saved links.
- Reader: 25 focused Andrews and layout-context checks passed, including inserted spaces, damaged digits, conflicting signs, combined ambiguous numbers and unchanged originals.
- Frontend: 18 directory/suggestion checks and 17 grouped-payment checks passed. All matching payments are selected, drafts survive refresh, a lost response reloads revisions, and printed-name paging retains underlying records.
- Actual browser: all 2,700 synthetic payments linked in about 3.5 seconds. A simulated lost successful response retained the draft and blocked a stale retry. Exact totals, unchanged payment records and 2,700 history events were independently read back.
- Actual browser: a temporary source failure during a 50-finding report download produced no incomplete package. Retry produced the same members and bytes as the previously verified package, including all supporting PDFs. The saved report did not change.
- Actual browser: the existing 5,000-payment case remained available after refresh without another import. The compiled build passed the 2,700-payment directory, last page, grouped original-name paging and corrected source readings with no writes or JavaScript errors.
- Checklist: desktop and phone layouts inspected; PDF downloads and ZIP copies match the checked synthetic originals. Guide link opens separately.
- Scoped lint, TypeScript checking and production build passed. Final bundling took 7.75 seconds with the existing large-chunk warning. No full suite was repeated.

## Deployment and remaining acceptance

The user authorizes verified daytime fixes to be pushed through the existing automatic deployment. Record the pushed commit and returned server identifier in the build state. A public frontend identifier and downloadable assets do not establish that an authenticated live case journey passed. Team UI acceptance and approved independent real-statement references remain separate outstanding acceptance work.

Ten-minute continuation checks stay active through 18:00 Europe/Dublin. Stop starting optional changes at 17:00, finish any necessary fixes and deployment checks, and leave a clear evening handoff. Do not repeat successful imports or report saves to fill the schedule.
