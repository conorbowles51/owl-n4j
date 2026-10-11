# r5-any-layout — WIP notes (real wave 5) — INTERIM, being updated

Counts and opaque ids only. Private detail (surveys, dev tools, frozen code copies) under
`/mnt/owl-data/fin-real/tmp/r5/`, benchmark runs under `/mnt/owl-data/fin-real/bench/r5-*`.
Branch `fin/r5-any-layout`, based on fin/release-1 b484f376. Not pushed. Backend-only changes so far
(no evidence-engine change, no reading revision bump; wave-4 readings reused).

## Landed so far

| Commit | What |
|---|---|
| 712282cb | Step 0.1: re-apply r4-any-layout (revert of the revert 2a9ba3ab) |
| 921ef1f5 | Step 0.2/0.3: holder never from movement text (heading cut at the first movement table; money/date lines never in an address block; postal line must read as one); printed account number beats the 18-digit interbank number containing it (`account_basis`) |
| 5fd0f3b8 | Holder confirmed by a second printed fact: addressee block reprinted in a postal-anchored fiscal block; CFDI receipt recipient agreeing with a heading line |
| dd69be91 | Scan-noise glyph at an address edge; Scotiabank + Kapital institution profiles |
| 82c0dcc1 | Section re-opened by its own repeated opening (D6); routing row-level scope on shared pages; institution equality without generic banking words |
| 08255ade | Scan damage: decimal mark split by a space; date letter confusions (Q, L/I, ~, 0CT); cut date + day count period |

## Measured so far (private engine survey, 567 truth documents, wave-4 readings, engine + profiles)

- Engine-proved periods matched to truth: 860 -> 866; holder equal to truth 745 -> 759, holder differing
  1 -> 0 (the wrong admission); every newly proved period equal to truth (period, opening, closing, rows).
- Routing survey: exactly 5 periods change (Intercam/Kapital quiet dollar sections now engine-served).
- Whole-set benchmark on step-0 code (921ef1f5) running: bench/r5-s0 (corpus copy bench/r5-corpus = the 567
  documents with wave-4 readings; the shared truth manifest gained t-visual-v17 documents meanwhile).

## Next

Final whole-set benchmark on final code; Santander/BBVA residue; census; generic-only figure.
