# Manual-change feed

Every time a person changes, confirms or sets aside something Loupe produced, the change is recorded once and
reaches the lesson job (`fin-lessons`) as lesson work. Repeats of one misreading are one lesson item with a count
and every link.

## How a change travels

1. **Record.** The save calls `services.manual_changes.record_change(session, kind, case_id, subject, before, after,
   actor, reason, link, pattern_key)` (or `record_confirmation(...)`). A route can carry `@records('<kind>',
   'change'|'confirm'|'set_aside', ...)` instead: it records after the route returns, on a database session of its
   own, so the route's own session and response are untouched. A row goes into `manual_changes`.
2. **Inbox line.** Once the save's outermost transaction commits, one JSON line per record is appended to
   `headless/MANUAL-CHANGES.jsonl`. A save that is refused or rolled back writes no row and no line. A failed record
   or append never fails the save; it is logged.
3. **Catch-up.** Every 10 minutes the watchdog runs `python -m services.manual_changes --check`, which appends any
   recorded change whose line is missing and reports what is still missing.
4. **Grouping.** Every watchdog cycle `headless/manual-change-lessons.py` groups the lines by `pattern_key` =
   kind | field changed | the reader or rule that produced the value | the layout fingerprint or bank. A pattern
   gets one message in `fin-lessons`' inbox; repeats update its page `headless/manual-change-patterns/<slug>.md`
   (count and every change with its link) and send nothing. Once the message is answered, a repeat opens a new
   message "recurred after <commit>".
5. **Not delivered.** Changes by the automated-checks logins, and changes in the verification case whose reason
   says test, are recorded with `test=true` and counted, never delivered. Judgement corrections keep their own
   inbox (`JUDGEMENT-CORRECTIONS.md`, line format unchanged) and are counted here. Undoing a person's own decision
   and personal view settings are counted, not lessons. Confirmations are counted per pattern and per kind.
6. **Board.** The status board shows "Manual changes not yet turned into lessons: N patterns (M changes)" beside
   the judgement line, and any append, catch-up or delivery error.

A person is the actor only when the record names no model and no system: entries made by Claude or DeepSeek on
someone's behalf, by "System" or "Batch review", or by a `@system.local` address are not manual changes.

## Why a feed of its own, not the audit chain

The audit chain (`financial_audit_events`) records row changes on 19 tables, made by triggers. It does not cover
`financial_judgements`, `financial_payment_categories`, `financial_category_rules`,
`financial_import_batch_items`, `financial_import_batches.files`, the graph (Neo4j), `graph_recycle_bin_items`,
`rejected_merge_pairs`, `significant_entities` or `workspace_ai_outputs`, and a row change does not say whether a
person decided it or a reader, a re-read or a sweep wrote it. Each route that takes a person's decision therefore
records it, in that route.

## Inventory

Columns: **kind**; the route or save that records it; **type** (change, confirm, set aside); **audit**: whether the
route's write also lands in the audit chain; **before → after**; **saved**: changes people saved before the feed
existed on the 6 financial cases (recorded as historic by the backfill; automated logins and model work excluded;
"–" where nothing kept the decision, so it could not be counted).

### Financial: ledger rows and documents

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `transaction_correction` | POST /api/financial/transactions/{id}/correction | change | yes | the row as read → the corrected row (replacement row) | 0 |
| `payment_edit` | POST /api/financial/ledger/payment-edits/confirm | change | yes | selected payments' fields → edited fields | – |
| `quarantine` | POST /api/financial/transactions/{id}/quarantine | set aside | yes | admitted → quarantined | 0 |
| `release` | POST /api/financial/transactions/{id}/release | change | yes | quarantined → admitted | 0 |
| `file_admit` | POST /api/financial/files/{id}/admit | change | yes | router finding → admitted to the document pipeline | 1 |
| `duplicate_decision` | POST /api/financial/documents/{id}/duplicate-decision | set aside / change | yes | counted copy → superseded (or restored) | 9 |
| `duplicate_keep_copy` | POST /api/financial/documents/{id}/keep-duplicate-copy | change | yes | which copy counts | – |
| `reader_replacement_restore` | POST /api/financial/documents/{id}/restore-replaced-statement | set aside | yes | a re-reading → the earlier reading | – |
| `candidate_review` | POST /api/financial/candidates/{id}/review | change / confirm / set aside | yes | candidate reading → reviewed reading | – |
| `candidate_finalize` | POST /api/financial/candidate-sources/{file}/finalize | confirm | yes | reviewed candidates → ledger rows | – |
| `statement_draft_edit` | PUT /api/financial/candidate-sources/{file}/statement-draft | change | yes | draft controls → edited controls | – |
| `model_attempt_abandon` | POST /api/financial/model-nominations/{id}/abandon | set aside | no | pending model reading → abandoned | – |

### Financial: names, categories, parties, accounts

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `payment_label_change` | PUT /api/financial/ledger/payment-labels | change | yes (row metadata) | name or category read → person's name or category | 27 |
| `payment_label_confirm` | POST /api/financial/ledger/payment-labels/confirm | confirm | yes (row metadata) | model's name, confirmed | 0 |
| `payment_label_remove` | POST /api/financial/ledger/payment-labels/remove | set aside | yes (row metadata) | saved name → earlier name or the statement's reading | 0 |
| `category_apply_like` | POST /api/financial/ledger/payment-categories/apply-like | change | no | category on like payments → chosen category | – |
| `category_rule_save` | POST /api/financial/ledger/payment-categories/rules | change | no | no rule → a rule placing future payments | – |
| `category_rule_retire` | POST /api/financial/ledger/payment-categories/rules/{id}/retire | set aside | no | active rule → retired | – |
| `account_party` | POST /api/financial/account-parties | change | yes | account's party → chosen party | 0 |
| `counterparty_party` | POST /api/financial/counterparty-parties | change | yes | matched counterparty → chosen party | 2 |
| `account_identity` | POST /api/financial/account-identities | change | yes | identity review → decided identity | 0 |
| `account_consolidation` | POST /api/financial/account-consolidations | change | yes | two accounts → one | – |
| `account_consolidation_undo` | POST /api/financial/account-consolidations/undo | change (not a lesson) | yes | consolidated → separate | – |

### Financial: judgement calls

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `judgement_confirm` | POST /api/financial/judgements/{id}/confirm | confirm | no | open call → confirmed | 2 |
| `model_statement_confirm` | POST /api/financial/judgements/statements/{doc}/confirm | confirm | no | model's calls on a statement → confirmed | – |
| `judgement_correct` | POST /api/financial/judgements/{id}/correct; a category a person changes over the model's | change (own inbox) | no | the call → the correction (JUDGEMENT-CORRECTIONS.md) | – |
| `judgement_reopen` | POST /api/financial/judgements/{id}/reopen | change (not a lesson) | no | confirmed or corrected → open | – |

### Financial: statement import and the review queue

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `statement_review_edit` | PUT …/statement-import/{file}/progress; PUT …/batches/{b}/items/{i} (inside the save) | change | yes (file metadata) | the system's reading (first save) or the previous save → the saved review, one record per changed field | 471 |
| `statement_review_confirm` | POST …/batches/{b}/items/{i}/confirm | confirm | yes | reviewed statement → imported | – |
| `statement_save` | POST …/statement-import/review/save | confirm | yes | ready statements saved as read | – |
| `page_rows_confirm` | POST …/batches/{b}/items/{i}/pages/{n}/confirm | confirm | yes | page's proposed rows → saved | – |
| `page_image_offer_accept` | POST …/page-image-offer/accept | confirm | yes | page-image reading offered → accepted | – |
| `page_image_offer_decline` | POST …/page-image-offer/decline | set aside | yes | offered → declined | – |
| `statement_account_details` | POST …/statement-import/account-details/save | change | yes (file metadata) | holder, number, institution as read → as set, per field | 179 |
| `field_proposal_group` | POST …/review/proposal-groups/confirm | confirm | yes (file metadata) | proposed value for empty fields → saved | – |
| `statement_details` | PUT …/statement-import/sources/{id}/details | change | yes | saved statement's details → corrected, per field | 295 |
| `statement_section_split` | POST …/sources/{id}/recovery/save | change | yes | saved statement → split sections | – |
| `account_type` | POST …/accounts/{id}/type | change | yes | account type → chosen type | 0 |
| `row_direction_flip` | POST …/accounts/{id}/type/flip-rows | change | yes | row direction → flipped | – |
| `account_details` | POST …/accounts/{id}/details | change | yes | account holder, number, institution → corrected | 0 |
| `account_details_confirm` | POST …/accounts/{id}/details/confirm | confirm | yes | a correction → confirmed | 2 |
| `account_details_undo` | POST …/accounts/{id}/details/undo | set aside | yes | a correction → undone | 0 |
| `duplicate_disposition` | POST …/statement-import/{file}/duplicate-disposition | set aside / change | yes (file metadata) | possible duplicate → ignored or restored | 48 |
| `not_payment_statement` | POST …/{file}/not-payment-statement | set aside / change | yes (file metadata) | statement → set aside as not a payment statement (or restored) | 0 |
| `payment_document_review` | POST …/{file}/payment-document/save | confirm | yes | proposed payment fields → saved note | – |
| `manual_payment` | POST …/sources/{id}/manual-payment | change | yes | no row → a row the person added | 2 |
| `record_withdrawal` | POST …/sources/{id}/withdraw-record | set aside | yes | record → withdrawn | – |
| `record_restore` | POST …/sources/{id}/restore-record | change | yes | withdrawn → restored | – |
| `record_completion` | POST …/sources/{id}/complete-record | change | yes | incomplete record as read → completed, per field | 11 |
| `row_assignment` | POST …/{file}/row-assignment/apply | change | yes (file metadata) | rows' statement → another statement | – |
| `review_recovery_ack` | POST …/{file}/previous-reviews/compare | confirm | yes (file metadata) | earlier review against the new reading → acknowledged | 2 |
| `statement_currency` | POST …/batches/{b}/currency | change | yes (file metadata) | currency → chosen | – |
| `file_currency` | POST …/batches/{b}/files/{src}/currency | change | no | file currency → chosen | – |
| `layout_memory_confirm` | POST …/layout-memory/confirm | confirm | yes (file metadata) | empty field → value remembered for the layout | – |
| `layout_memory_withdraw` | POST …/layout-memory/{id}/withdraw | set aside | yes (file metadata) | remembered value → withdrawn | – |
| `batch_item_skip` | POST …/batches/{b}/items/{i}/import-choice | set aside / change | no | statement → skipped (or restored) | 2 |

### Financial: the graph-backed view

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `transaction_category` | PUT /api/financial/categorize/{key}; PUT …/batch-categorize | change | no (graph) | category → chosen | – |
| `transaction_from_to` | PUT /api/financial/from-to/{key}; PUT …/batch-from-to | change | no (graph) | from/to → chosen entities | – |
| `transaction_details` | PUT /api/financial/details/{key} | change | no (graph) | purpose, details, notes → set | – |
| `transaction_amount` | PUT /api/financial/transactions/{key}/amount | change | no (graph) | amount → corrected (original kept) | – |
| `transaction_bulk_correct` | POST /api/financial/transactions/bulk-correct | change | no (graph) | fields → corrected | – |
| `sub_transaction_link` | POST /api/financial/transactions/{key}/sub-transactions | change | no (graph) | no parent → parent | – |
| `sub_transaction_unlink` | DELETE /api/financial/transactions/{key}/parent | set aside | no (graph) | parent → none | – |

### Graph and entities

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `entity_property_edit` | PUT /api/graph/node/{key}; PUT /api/graph/batch-update | change | no | extracted properties → edited | – |
| `entity_location_correct` | PUT /api/graph/node/{key}/location | change | no | geocoded location → moved | – |
| `entity_location_remove` | DELETE /api/graph/node/{key}/location | set aside | no | location → removed | – |
| `insight_confirm` | POST /api/graph/node/{key}/verify-insight | confirm | no | AI insight → verified fact | – |
| `insight_reject` | DELETE /api/graph/node/{key}/insights/{i} | set aside | no | AI insight → removed | – |
| `fact_pin` | PUT /api/graph/node/{key}/pin-fact | confirm | no | fact → pinned | – |
| `entity_merge` | POST /api/graph/merge-entities | change | no | separate entities → merged | – |
| `merge_suggestion_reject` | POST /api/graph/reject-merge | set aside | no | suggested duplicate pair → rejected | 0 |
| `merge_suggestion_unreject` | DELETE /api/graph/rejected-merges/{id} | change (not a lesson) | no | rejection → undone | – |
| `entity_delete` | DELETE /api/graph/node/{key} | set aside | no | extracted entity → recycle bin | 79 |
| `entity_restore` | POST /api/graph/recycle-bin/{key}/restore | change | no | recycle bin → restored | – |
| `significant_entity_add` | POST /api/significant/{case}/entities:batch | confirm | no | entity → significant | – |
| `significant_entity_remove` | POST /api/significant/{case}/entities:remove | set aside | no | significant → removed | – |
| `significant_entity_clear` | DELETE /api/significant/{case} | set aside | no | all significant → cleared | – |

### Evidence, phones, workspace, timeline

| kind | recorded by | type | audit | before → after | saved |
|---|---|---|---|---|---|
| `transcript_speaker_correct` | PUT /api/evidence/{id}/transcript-speakers | change | yes (evidence_files) | diarized speaker labels → named or merged | – |
| `evidence_relevance_set` | PUT /api/evidence/relevance | set aside / change | yes (evidence_files) | relevant → not relevant (or back) | – |
| `device_name_override` | PATCH /api/cellebrite/reports/{key} | change | no (graph) | parsed device name → override | – |
| `workspace_ai_accept` | POST /api/workspace/{case}/ai-outputs/{id}/accept | confirm | no | AI output → accepted | 2 |
| `workspace_ai_reject` | POST /api/workspace/{case}/ai-outputs/{id}/reject | set aside | no | AI output → rejected | 0 |
| `attention_dismiss` | PUT /api/workspace/{case}/attention/{key} | set aside (not a lesson) | no | attention item → dismissed or snoozed for that person | – |
| `attention_clear` | DELETE /api/workspace/{case}/attention/{key} | change (not a lesson) | no | dismissal → cleared | – |
| `timeline_event_add` | POST /api/timeline/entries | confirm | no | generated event → added to the timeline | – |

The 6 financial cases hold 1,134 historic records by people. Kinds marked "–" leave no stored decision with its person
that the backfill can read (for example category rules, graph property edits, insight decisions, the timeline and
attention items); they are recorded from the feed onward. A historic statement-review save is compared against the
reading it was made on; when that file has since been removed or re-read, the record says "(not compared: …)" and
counts as one change of that pattern.

## Test and verification changes

A change by `jobs-verify@loupe.invalid` or `ui-walkthrough@loupe.invalid`, or a change in the verification case
`cded78d0` whose reason says test, carries `test=true`. It is stored, appended and counted on the board ("test
changes not delivered") and never sent to `fin-lessons`.
