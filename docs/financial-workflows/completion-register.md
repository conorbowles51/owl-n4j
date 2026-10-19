# Financial and ingestion completion register

Updated 23 September 2026. This register supersedes the earlier partial-release
claim for `a465f6fc`. Implementation, local checks and live acceptance are separate.
Client evidence, screenshots, case exports and credentials are excluded from Git.

**Latest feedback implementation:** All F01–F28 items, including retained review filters/active rows and typed Paid by/to identity links, are implemented and locally verified. The [current acceptance record](implementation-progress-2026-09-23.md) maps every report to its connected journey and evidence, including a real-service browser test that uncovered and verified the repeated bulk-correction repair. Publication of this pass and independent live acceptance remain distinct from the previous release below.

Deployment status: the user confirmed on 23 September 2026 that deployment has
happened. Do not list deployment as pending or infer otherwise from this agent's
earlier access failure. Independent live acceptance below remains separate.

| Investigator journey | Implementation and local verification | Remaining external acceptance |
|---|---|---|
| Select PDFs or open a batch → bulk set/edit account details → review changes → save → reopen | Added after Alex's 23 September report. Shared editor covers holder, account number, bank, currency and dates; defaults to filling missing values. Imported and unimported statements share preview, atomic save, history, retry receipts and retained selection. Tested with isolated SQL and Chromium journeys. | Push triggers automatic deployment. Independent live acceptance of this new addition remains separate from the user's confirmed deployment of the earlier release. |
| Previously combined import → separate printed accounts/currencies → preview → save → reopen | Connected recovery retains original readings, investigator edits and citations; every current payment/incomplete record is assigned exactly once. Atomic replacement, exact amount rescaling without FX, stale-preview refusal and idempotent receipts are covered by SQL and Chromium tests. | Review the affected existing case records with authorized live access. No client import has been rewritten for demonstration. |
| Upload files/folders/archives → pause → leave → reselect → resume → one registration | Complete selection manifests, verified chunks, retained paths, safe archive expansion and atomic registration receipts. Financial multi-PDF upload uses the same retained path. Browser return/resume and failed/lost registration responses are covered. | Verify on deployed infrastructure and representative real uploads. |
| AI ingestion alongside Financial reading → pause/interruption → resume | Separate processing queues; durable page/work-unit checkpoints. Phone-report ingestion now checkpoints parsed models, graph/media writes and dispatch receipts. Financial batch preparation/imports stop at statement boundaries; already running PDF readings have separate controls on the batch page. Synthetic concurrent browser/worker and real isolated graph checks pass. | Actual long chat through live providers, interruption and final source counts; historical timeout diagnosis needs live logs. |
| Transfer with split entries/fees/partial amounts → onward allocation → reopen | Explicit principal, fees and unassigned amounts; capacity checks across saved links; explicit cross-currency comparison. Internal totals count reviewed principal once; fees/residual remain external. Timeline preserves partial original entries. Browser save/reopen and SQL arithmetic/retry checks pass. | Deployed workflow verification. |
| One-sided transfer → later statement → review possible match → update original link | Typed identifiers locate possible opposite entries when statements arrive. Review still checks amount/date/reference; the existing saved link is updated without inventing a posting or duplicating a transfer. SQL save/reopen verified. | Deployed review with actual later statements. |
| Establish account identity/ownership → reuse throughout case | Typed identifier aliases, referenced accounts without invented balances/payments, audited links to existing case entities. Reviewed holder/control/signatory/grouping remain distinct. Retrying graph projection preserves manual names/notes and retracts only managed links; namespace conflicts fail safely. SQL, Chromium and isolated Neo4j checks pass. | Confirm deployed graph synchronization and linked destinations. |
| Duplicate/missing-import incident → compare history/counts → recover same case | Internal reading lineage groups one original in Evidence; independent uploads remain distinct. Reviewed removal/recovery retains source/history. Prevention and correction paths are implemented and locally tested. | Read-only audit of the reported existing duplicates and import attempt; any record-specific correction requires a reviewed scope. |
| Release while colleagues ingest → deployed checks | Code-only release checks cover migrations, build, targeted lint, backend/engine and connected browser journeys. Deployment confirmed by the user on 23 September. | Independently record the running revision, health and live workflow checks. Earlier access failures do not mean deployment is pending. |

All implementation applies across cases and future ingestions; there are no
case-ID or source-filename production exceptions. The supplied bank layouts and
synthetic fixtures do not certify every possible bank format or every file in an
unavailable corpus. A local pass is not a deployed or live-accepted result.
