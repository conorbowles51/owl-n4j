# Statement ingestion: today's steps and what to remove

Scope: what an investigator does to get bank statement PDFs from upload to saved statements in Financial, counted
from the current screens (`StatementFilesPanel`, `EvidenceFinancialPicker`, `FinancialBatchPanel`,
`BulkStatementDetails`, `StatementImportPanel`). Counts of statements come from one real batch on case 49494305
(batch f6f7cd42: 109 files, 824 prepared statement reviews), used only as an example of scale.

## 1. The steps today

| # | Step | Screen | Clicks / decisions |
|---|------|--------|--------------------|
| 1 | Get the PDFs into Financial: either upload in **Files in Financial** (choose files, upload runs, reading starts by itself), or **Choose from Evidence** (browse folders, tick files or folders, *Review selected files*, check the list, *Send N files to Financial*). | Files register, or Evidence picker dialog | Upload: 2. Evidence picker: 4 + one tick per file or folder. |
| 2 | Wait for reading (text layer or OCR) to finish. | Files register | 0 clicks, but the investigator must come back. |
| 3 | Start a batch (upload route only): tick files (*Select all N shown files*) and press *Review and save selected files together*, or *Start batch check of N read files*. Decide which files belong together. Before this step: if the files are already in an unfinished batch, the screen now asks whether to continue it (default) or start a fresh one. | Files register | 2, plus 1 decision. |
| 4 | Wait for batch preparation. | Batch review | 0 clicks, come back again. |
| 5 | Save the statements that passed every check: *Save N ready statements*. | Batch review | 1 per batch (190 of 824 in the example). |
| 6 | Fill details that are missing across many statements, one reason at a time: *Resolve N together* opens a dialog; choose the account, select its periods, type the value (holder, account number, bank, currency, dates, or confirm no activity), *Preview*, *Save*. | Batch review → group dialog | About 5 per reason per account. In the example: currency 299 statements, account number 102, bank 83, holder 65, no activity 22 (one statement can need several). |
| 7 | Open each statement that has a reading, balance, assignment or duplicate check: inspect the flagged row against the PDF, edit or mark the row, *Save for bulk import*, *Next unfinished statement*. | Statement review | 3 to 10 per statement. In the example: reading 201, balance 194, assignment 23, possible duplicate 20. |
| 8 | Return to the batch and save again (step 5) as statements become ready. | Batch review | 1 per round. |
| 9 | Copies of statements kept elsewhere are set aside automatically and are now named on the batch screen and on each file card before anything is opened (102 of 824 in the example: two whole files). | Batch review, Files register | 0 (previously each copy had to be opened to find out). |

Screens visited: Files register, Evidence picker (two views), batch list, batch review, group dialog, statement review —
six, with two waits in between. Decisions the investigator makes: which files form a batch, whether to continue an
existing batch, one value per missing detail per account, and a judgement per flagged row.

The two places that list work (the Files register "Needs action" filter and the batch review's reason groups) count
it differently, so the investigator can be sent to the same statement from two directions.

## 2. What to remove or automate, ranked by investigator time saved

| Rank | Change | What it removes | Cost |
|------|--------|-----------------|------|
| 1 | **Propose the currency.** Take it from the printed currency (symbol or code on the statement), else from the same account's saved statements, else the case's usual currency; show one prefilled confirmation per account ("USD for 299 statements — confirm"). | Most of step 6 in the example: 299 of the 532 blocked statements wait only for a currency choice. | Medium. The group dialog and currency save exist; the proposal logic is new. |
| 2 | **Start the batch by itself after upload reading.** When the files of one upload finish reading, prepare them (or continue the open batch that holds them) without step 3. | Step 3 and one of the two waits. | Cheap. The upload queue already knows the file ids; the batch start and continue logic exists. |
| 3 | **Prefill bank, holder and account number** from the same file's other periods and from saved statements with the same printed account number; one confirmation per account, as in rank 1. | Most of the rest of step 6 (83 + 65 + 102 statements in the example). | Medium. Grouping exists; the proposal is new. |
| 4 | **Collapse overlapping batches in the batch list.** Hide (not delete) a batch whose files are all held by a newer unfinished batch, and show one line per set of files. The example case has 19 batches and one file appears in up to 7. | Choosing between near-identical batches; re-checking the same statements in two places. | Cheap to medium. The overlap check used when starting a batch already computes this. |
| 5 | **One work queue.** Make the Files register's "Needs action" open the batch review filtered to that file instead of keeping a second, differently counted list. | The double route into the same statement. | Medium. |
| 6 | **Save fully reconciled statements without a click.** A statement whose balances agree with every transaction and has no other check could be saved when preparation ends. | Steps 5 and 8. | Cheap technically. Needs a decision: today saving is always an investigator action. |
| 7 | **Run "check for additional statement periods" and refreshes automatically** after preparation and after each correction. | Two buttons the investigator must know to press. | Cheap. |
| 8 | **Fewer reading and balance checks** by fixing the readers (the real-document programme). | Step 7 for most statements. | Expensive; already under way. |

Already in place: copies are announced before opening (step 9), and starting a batch over files already in an
unfinished batch offers to continue it, with a fresh batch as a separate, explicit choice. In the example, a new
selection of the same 109 files would have been offered the unfinished batch from 6 Oct that already holds all 109.
