# t-visual-v11 — WIP notes (counts and opaque ids only)

Unit: visual confirmation of visual-queue shard v11 (capital-one-card, 1 document d22e405327ccf, 222 pages, 8 periods
`ocr_reconciled`), then a BLIND measurement of fin/release-1 after integrate-13 on them. Branch fin/t-visual-v11 from
643d5ed5. Not pushed. **No processor code changed**: two truth-tooling commits under backend/benchmarks/, with tests.
Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v11.md, truth/visual/d22e405327ccf.txt|.json,
tmp/v11/ (renders, sheets, text-layer dump, old-code check), truth-mini-v11, bench/v11-mini, bench/v11-mini-generic-only,
tmp/v11/mini-compare*, logs/v11-*.log; backups truth-backup-pre-v11/ (manifest, status, queue, periods, Merrick
transcription), tmp/v11/manifest-before-d5a3.json, tmp/v11/manifest-before-run3.json.

## Landed (commits)

| commit | change |
|---|---|
| 7b9b88b4 | real_visual: `confirm <n> <digest>`: an `ocr_reconciled` text-layer period whose every value was found equal on the page images becomes verified with its reading unchanged (post dates, undated interest lines kept, so it is stored like the document's other verified periods; a `patch` retype would lose both). Refused unless the period is still `ocr_reconciled`, all its pages are on `done` and the reading still has the digest (dates, account, holder, currency, balances, printed summary, every row). `digest` subcommand prints the line. |
| 1e4c38ca | real_visual: a review carrying confirm lines writes `complete=false, complete_with_confirm=true`; only code with `ready()` applies it. Code that predates confirm leaves the document at its text-layer reading (fail closed) instead of reading "complete, no periods" as "no statements". Root cause below. No empty `visual_confirmed` key on documents with nothing confirmed. |
| (this) | WIP-NOTES.md |

## Visual confirmation: COMPLETE (all 8 periods final)

- All pages of the 8 periods rendered (fitz, 150 dpi; 300 dpi crops where needed) and read: statement pages in full,
  plus every other page (privacy notice, reverse-side terms, referral inserts, a billing-cycle notice), none of which
  carries a ledger value.
- **Image vs text layer: equal on every value, 0 misreads**: 45 rows (date, post date where printed, amount, direction),
  8 x 8 summary fields, the printed transaction totals, fee totals and interest lines, holder and account digits.
- Every one reconciles to the cent and matches every printed control.
- Final status: **#2 #3 #13 #14 #15 #27 #39 #51 all verified**. Expected outcomes: auto 7, duplicate 1 (#13 is the same
  printed statement as #12). Recorded by `confirm`; reverse in one line of the private transcription.
- #2 prints "Page 1 of 4"/"2 of 4". Pages 3-4 carry no number (the notice before page 1, the privacy notice after
  page 2). The ledger closes on page 2 (transaction, fee and interest totals, year-to-date block), so no ledger row
  can sit on the unnumbered pages. The tier-A reader ignores page totals on this family, as for the 45 already
  verified. Reverse: `keep 2 hold ...`.
- **#12 (open decision 4, live disagreement): the image agrees with its current truth** (summary, 1 payment, interest).
  Truth unchanged.

## Shared truth

- Regenerated `--only d22e405327ccf` (3 runs, see incidents). The document is now verified: **53/53 periods verified**
  (45 + 8), manifest truth_complete true. Visual queue: v11 done (353/353 with v12).
- **Statement documents final 832/832** (verified 793, settled 4, unverified 18, not_statement 17). t-visual-v12's 2
  documents were also final on disk (from its own complete transcriptions). **Verified periods 1,897 -> 1,917**
  (+8 this unit, +12 v12); ocr_reconciled 20 -> 0; unverified 33, incomplete 3.
- Against my backup, only these documents differ: d22e405327ccf (8 statuses), v12's df7e9c5f8cbb0 and df9292c6e6c36
  (v12's own patches), and v12 part B's additions (18 new unscored manifest entries + dfc15d7fbdc2c), which are kept
  exactly as v12 wrote them.

### Incidents found and repaired (the next truth writer must know these)

1. **Old code drops a confirm-only document's periods.** At 04:16:45, another unit's real_truth run, on code
   without confirm, merged my first visual file. That file was complete with no transcribed periods, so the old
   code replaced the document's 53 periods with none (status unverified, manifest entry gone). Fixed in 1e4c38ca
   and checked against the 643d5ed5 module: old code now leaves the document unchanged (53 periods, partly_verified).
   **Until the integration merges 1e4c38ca, any truth write on older code puts this document back to 45 verified +
   8 ocr_reconciled (nothing lost). Re-run `real_truth --only d22e405327ccf` on merged code to restore 53/53.**
2. **real_truth rebuilds manifest.json from periods/*.json.** Two kinds of entry exist only in the manifest, and every
   write drops them:
   (a) r13-merrick's hand edit of d5a3ad9b75a08#8 (one row date, from the image). Dropped by my first run, then fixed
   durably: the date is now in that document's transcription (line 189, re-checked on the image at 300 dpi; prints
   the corrected day), the transcription was recompiled (42 verified, unchanged otherwise) and the periods cache
   regenerated. Its manifest entry, with the note, was restored from backup.
   (b) v12 part B's 18 unscored all-unverified documents (and its dfc15d7fbdc2c change). Dropped by my third run,
   restored entry by entry from a snapshot taken just before it (only d22e405327ccf differs from that snapshot).
   **Part B's entries will be dropped again by any later real_truth write until write_outputs carries them**
   (v12 or the integration should check this, or make write_outputs keep them).

## BLIND measurement (code 1e4c38ca = fin/release-1 after integrate-13 + truth tooling only; no tuning)

Mini corpus truth-mini-v11 (1 PDF, 53 periods: 52 distinct + 1 copy, all verified). `--readings` tmp/int13/readings-w13.json
(no fresh read), compare into tmp/v11/mini-compare*.
- **Product: ready 52/52 (100%), WRONG 0**, all saved automatically; critical-field errors 0 (299 rows); copies held
  1/1; valid-looking wrong values 0; unmatched items 0. **53/53 periods compared with no disagreement.**
  The 8: **7 ready, #13 held as an exact copy (expected duplicate)**. Other 45 periods: unchanged vs bench/wave13.
- **Generic-only (LOUPE_FINANCIAL_GENERIC_ONLY=1): ready 44/52, WRONG 0**, 245 rows, 0 critical. The 8: 7 ready; #13
  and #12 held as copies (attention, duplicate). Other periods vs bench/wave13-generic-only: same outcomes. 6 held periods
  (#37 #38 #45 #46 #47 #52) lose their "duplicate" reason and stay held for reading 2 / balance 1. Cause: the mini
  corpus lacks the other Capital One documents those copies matched, not a code change. Comparison: 45/53 without
  disagreement (classes only in held periods: not_ready 8, row_extra 12, holder_missing 1).
- Neil ruling 2 (late-posted card charges): in this document's truth, **16 rows are dated before their cycle start
  (12 of 53 periods)**. The product keeps every one with its printed date (0 date disagreements). No processor change
  was made here. A whole-set before/after count belongs to a unit that changes the rule.

## Tests actually run

- test_financial_benchmark_corpus + real_truth + real_visual + real_compare + statement_census: **121 OK** after
  7b9b88b4 (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). After 1e4c38ca:
  test_financial_real_visual **45 OK**. 6 new tests in total.
- Old-code compatibility: the 643d5ed5 real_visual's apply_visual on the new visual file returns the result unchanged.
- Synthetic statement benchmark not run: no processor or harness code changed (only the visual-truth merge).
- Full financial suite not run (no processor module changed).

## Next units should continue with

1. Integration: merge 7b9b88b4 + 1e4c38ca, then `real_truth --only d22e405327ccf` on merged code if a write on older
   code has put the document back to partly_verified (check status.json first).
2. Make `write_outputs` keep manifest-only entries (v12 part B's unscored documents) or move them into the
   periods cache, so no truth write drops them. A hand edit to manifest.json is lost on the next write: put
   corrections in the visual transcription instead.
3. Truth coverage is complete (832/832). The next whole-set run scores this document's 8 new periods: expect +7 ready
   (product) if it agrees with this blind run.

## Decisions needed from Neil

- None. Decided here (reversible in one line of the private transcription): #2's unnumbered "of 4" pages do not
  hold ledger rows (the ledger closes on its page 2), so the period is verified rather than held.
