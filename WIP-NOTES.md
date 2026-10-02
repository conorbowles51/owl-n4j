# fe-triage: WIP notes (2026-10-02)

Branch `fin/fe-triage`, based on `fin/release-1` (64db6a5f). Not pushed, not merged.

## Landed

- `bec39327`: Source audit test now waits for results-heading focus without running a 1 s role query on every check. Test-only change.
- `6484e448`: Unit test budgets now match the measured cost of role queries in jsdom. testing-library `asyncUtilTimeout` is 10 s (in `src/test/setup.ts`), the unit project `testTimeout` is 60 s (in `vitest.config.ts`), and the explicit 20 s on FinancialPage "retains the selected PDF" is removed.

## Before / after

- Before (release-1 log): 8 files and 15 tests failed, out of 295 files and 2052 tests.
- After: **295/295 files and 2052/2052 tests passed, twice in a row** (unit project). Run 1 took 692 s with the worst test at 34.1 s. Run 2 took 560 s with the worst test at 24.5 s.
- `npx tsc -b` returned 0.

## Triage of the 15 failures

Every file was run alone first.

- 13 were 5 s test timeouts. One more (FinancialPage "retains the selected PDF") hit its own 20 s budget.
- 2 were `findByRole("option")` waits that hit testing-library's 1 s default under suite load (PdfCandidatesPanel, SourceCustodyPanel). Both pass alone.
- 1 was a `toHaveFocus` failure (FinancialSourceAudit "finds the exact file family"). This was the suspected a11y bug in StatementFilesPanel, and **it is not a component bug.** Instrumentation showed `document.activeElement` is the H3 "1 matching files" one animation frame after "Find in files". The test looked up the heading by role inside `waitFor`. Each lookup took 1.2 s, longer than the whole 1 s wait, so the focus frame never got to run between checks. Fixed in the test.
- No stale assertions and no component regressions from the 29 Sept / release-1 changes were found.

## Root cause of the slowness (measured)

- jsdom 28 recomputes styles after every DOM change. Each element is matched against jsdom's default stylesheet plus Sonner's injected 97 rules (`style-rules.js`).
- On the financial screens one role query costs 1.2–1.8 s with no other load (634–1228 nodes). Removing Sonner's sheet only lowers that from 1.0 s to 0.7 s.
- The 2700-row LedgerRowBrowser test builds its fixture in 1 ms and renders one 50-row page. 8.5 s of its 10 s is two `getByRole(button, {name})` calls.
- The 1201-connection graph test takes 3 s alone. 1201 is load-bearing because it pages past the old 1200 cap, so it was left as is.
- I chose not to replace role queries with text or selector queries, because that would drop the accessibility checks these tests exist to make.

## Unverified / caveats

- The browser and storybook projects were not run. Only `src/test/setup.ts` is shared with the browser project, and a longer async wait is harmless there.
- eslint was not run.
- The 60 s budget has 1.75× headroom over the worst observed test (34 s at load average ~6 on 6 cores). A much busier box could still time out.

## Needs Neil

- Optional speed-up, not done: removing Sonner's injected stylesheet in the unit setup would make role queries about 30% faster. It would change toast visibility semantics in jsdom, so I left it.
