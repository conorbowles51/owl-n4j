# Larger statements, selections, graphs and reports

16 September 2026. Local implementation and verification of the four capacity changes requested before user testing. These changes have not been pushed or deployed.

## What changed

| Area | Previous restriction | Current behaviour |
| --- | --- | --- |
| One statement review | 1,000 possible transactions and 10,000 total extracted rows | 25,000 possible transactions and 100,000 total rows. Corrections show 50 rows per page. Confirmation counts every selected transaction, including other pages. Flagged rows open directly on the right correction page. |
| Named payment selection | 100 payments | Select all matching payments across table pages or all linked analysis payments. Source details are checked in batches of 500, then the entire selection is saved once. Saved details have a 32 MB size bound. Large saved selections have their own page controls. |
| Payment graph | 1,000 payments | All matching payments are retained. Repeated payments between the same account and name share an arrow, separately by currency and direction. Distinct connections show 250 per graph page. Search and the payment list cover the complete result. |
| Combined report | 20 findings and 8 MB of saved data | No finding-count restriction; up to 32 MB of saved report data. Findings load five at a time and retain the selected order. The ordering controls show 25 findings per page. Saved reports and downloads include all selected findings. |
| Original PDFs in a report package | 20 files | No file-count restriction. The existing 64 MB combined original-file bound remains. Payment source checks use the same bounded batch endpoint. |

The shared account/date calculation ceiling was raised from 10,000 to 100,000 rows so a newly supported statement is not immediately refused by totals or graph preparation. Graph preparation still uses the existing 64 MB complete ledger snapshot bound. A limit refusal does not return partial totals or a partial graph. These are resource bounds, not measured guarantees of performance at every maximum.

Statement drafts now store changed rows rather than a second copy of every unchanged reading. Previous complete drafts still reopen. This keeps a small correction in a large statement from filling browser-tab storage. The confirmation still sends the complete reviewed statement. Original source text, page locations and change explanations are preserved.

## Verification

- **Actual 5,000-payment statement:** generated and visually checked one 167-page synthetic PDF, uploaded it through the local application and confirmed its import once. The reader returned 5,000 transactions, 6,338 retained rows and no flagged problems. The import completed in about 15 seconds locally. A separate readback checked all 5,000 amounts, dates, directions, running balances and original page references against the generator. Money in was EUR 15,819.31, money out EUR 31,642.69, and the closing balance EUR 984,176.62.
- **Actual 2,700-payment selection:** selected the complete existing three-account test case, refreshed, saved and reopened it. Saving took about 1.7 seconds locally. All 2,700 unique payments and three source links were retained. The final page of a saved 900-payment source group remained accessible.
- **Actual payment graph:** loaded all 2,700 payments, drew paged connections and opened the complete underlying payment list. Automated checks additionally retained 25,000 payments and exact totals through connection grouping, and reached the final graph page among 1,201 distinct connections.
- **Actual 50-finding report:** selected findings across list pages, arranged the report through its second ordering page, previewed, saved, reopened after refresh and downloaded the report with all three PDFs. Preview took about 0.9 seconds and package download about 1.2 seconds locally. Independent ZIP verification found all 50 findings, all 2,700 selected payments with their exact dates, amounts, directions and balances, all original PDF bytes, and valid member and report hashes. Saved report data was 3,244,843 bytes.
- **Focused automated checks:** imported all 5,000 payments in the backend fixture, checked the 25,000-transaction request boundary and over-limit refusal, exercised case/digest/missing-record batch refusals and one-query source loading, preserved complete 1,200-row review submission after paging and edits, and saved/reopened/downloaded 250 findings. A separate package check included 25 original PDFs. Missing batches prevent partial selection saves.

The batch browser check exposed repeated loading of whole statement metadata for every joined payment. Source queries now select only the required document and file columns, and a regression check prevents that extra loading. Browser helper retries corrected menu navigation and a page selector's label/value ambiguity. They did not repeat successful imports, selections or reports.

All sources and mutations for this capacity verification were synthetic and local. Existing real PDFs were not changed or imported. This checks capacity and preservation of known data; it is not an independent accuracy measurement for arbitrary real bank statements.

## Testing and deployment

Scoped lint and the final TypeScript/production build passed. The final bundle took 13.22 seconds and retained the existing large-chunk warning. A read-only browser check against the compiled preview reopened the 5,000-payment case, the saved 50-finding report and the final graph page among 2,700 payments. The table rendered 50 rows at a time. No financial writes or JavaScript errors occurred. No full suite was repeated for this change.

The financial guide now describes the new controls and bounds. Completed work remains checked off in the completion plan. No database migration is needed for this change. The existing repository push remains the deployment trigger. Deployment and live verification have not been performed by this task.
