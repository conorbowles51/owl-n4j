# Loupe progress — 6 September 2026

The correction and source-review workflow is connected and tested in the local
application. The complete financial ingestion workflow is still unfinished.

## Working now

- Ledger and Held out support exact amount corrections with preview, a stated
  reason, stale-review protection and a recorded replacement. Originals remain
  visible in correction history. Existing quarantine is preserved.
- Both current rows and original/replacement history can open their cited
  evidence file and stored PDF page/highlight. Wrong-case links and changed
  recorded digests are refused. Missing locations are explained rather than
  guessed; renderer failures do not leave a misleading highlight.
- Source text can be selected and assessed for possible amount readings from
  evidence search or a ledger citation. Stored text origin governs the assessment.
  Unknown provenance remains uncertain. This is read-only and does not admit a
  transaction or automatically replace an amount.
- PDF extraction now carries text-origin metadata into canonical text storage.
  Existing texts without it remain unknown. Restart the engine and worker before
  exercising this change through a new extraction job.
- The isolated application runs in separate backend/engine venvs with synthetic
  Docker data. Backend PDF rendering is now installed and declared as a dependency.

## Verified

Latest passing baselines: **3,549 financial tests, zero skips; 895 frontend unit
tests; 11 Chromium tests.** TypeScript and ESLint pass. Live synthetic checks cover
correction history, held-out replacements, exact source assessments, rendered PDF
highlights, original-file delivery and source-render failure reporting.

Frontend, backend and engine returned HTTP 200 at the final availability check.
Open the application at http://127.0.0.1:55174. Local setup and repeatable checks
are in `docs/local-application.md`; fixture IDs and detailed test evidence are in
`docs/loupe-build-state.md`.

## Remaining

The PDF extraction path still lacks a source-bound mapping/candidate bridge into
the relational ledger. Automatic suspect flags cannot safely be added by treating
graph amounts or formatted ledger integers as original source text. The next
implementation contract is proposed in `docs/loupe-pdf-ledger-bridge.md`.

Native control and printed running-balance revalidation, the remaining duplicate
scope/coverage work and relational-to-graph projection also remain. External AI
processing and whole-application acceptance have not been validated.

All changes are committed locally on `integration/evidence-main-reunion`. Nothing
was pushed or merged to main, and real evidence/databases were not changed.
