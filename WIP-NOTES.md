# r-census — WIP notes (in progress; rewritten at the end of the unit)

## Landed (branch fin/r-census, not pushed)
- fb06e947 `scripts/financial_statement_census.py` (all-files census) + estimate refactor (`scratch_batch`).
- 37f44552 live periods counted once (legacy whole-file items, dateless summaries); system set-asides are not holds; `--rejoin`.
- af62dcc8 period identity = statement key, or account + printed dates (multi-account statements).

## Run in progress
`nohup` run of all 6 cases, log /mnt/owl-data/fin-real/census/logs/all2.log, private output
/mnt/owl-data/fin-real/census/<case>/, reading cache /mnt/owl-data/fin-real/census/readings/<engine tree>/.
If the run died: relaunch the same command (see the end of these notes); cached readings are reused.

## Interim findings (counts and opaque ids only)
- SAFETY GAP (verified in source + one real original, f887b0d9:9a66ffec8137, 54 pages): pages made of small image
  tiles (~10% of page area, mixed-raster scan compression) under an INVISIBLE OCR text layer (render mode 3, written
  by a third-party OCR tool) are classified `digital_text_layer` by `services/financial/suspect_amounts.page_text_origin`
  (rule: images must cover >= 80% of the page). So the money-cell crop verification for image-derived pages does not
  run on them, and `financial_ledger_misread_audit` skips them as native text. The producer's OCR layer does contain
  misreads (seen: a posting date with its slash read as "1"). Partial scan: 6 read originals have invisible text used
  as native pages. The synthetic corpus models invisible OCR layers only over ONE full-page raster, which the rule catches.
- credit-one-card on that original: retained (older) reading 52 ready, current reading 27 ready (current engine now
  takes the producer OCR layer on 52 pages where the older reading OCR'd 29 itself).
