# r-census — WIP notes (in progress; rewritten at the end of the unit)

## Landed (branch fin/r-census, not pushed)
- fb06e947 `scripts/financial_statement_census.py` (all-files census) + estimate refactor (`scratch_batch`).
- 37f44552 live periods counted once (legacy whole-file items, dateless summaries); system set-asides are not holds; `--rejoin`.
- af62dcc8 period identity = statement key, or account + printed dates (multi-account statements).

## Run in progress
`nohup` run of all 6 cases, log /mnt/owl-data/fin-real/census/logs/all2.log, private output
/mnt/owl-data/fin-real/census/<case>/, reading cache /mnt/owl-data/fin-real/census/readings/<engine tree>/.
If the run died: relaunch the same command (see the end of these notes); cached readings are reused.
