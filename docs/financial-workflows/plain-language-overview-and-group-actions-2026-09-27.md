# Plain-language statement progress and group actions

## Investigator objective

Understand what Loupe has saved, what is ready to save and what needs a correction; identify missing statement months; save ready statements together; copy source text into corrections without leaving the review.

## Connected changes

- Overview distinguishes files added, files with saved statements (including no-activity statements), files with none saved yet, statements ready to save together and statements needing a check. File counts cover the whole case, not just the payment filters.
- Per-account and currency coverage uses the existing server report of usable saved statement dates. Shows missing whole months, months with partial gaps, exact checked range and named missing months. Does not count duplicates twice or infer missing months before/after the known range. Account-review action opens the actual account section for an explicit date-range check. Account pages remain paginated; unsaved files may fill apparent gaps.
- Timing comparisons explain money coming in followed by the next recorded payment out within seven days. These are review examples, not suspicious-activity findings or traced funds.
- The statement list has a prominent ready count and group review/save action. It passes only files with available statements to existing guarded batch preparation, then opens its confirmation summary. Nothing imports merely by filtering or preparing a group. Saved corrections, duplicate checks and admission checks remain in the existing service.
- Ready file cards say not saved yet rather than relying on zero saved counts. Selected-file action explicitly offers group review and saving.
- The older-upload check is a short historical notice, with an action to current statement progress. Detailed scope is collapsed; prior-run counts are not represented as current unfinished work.
- Source images offer an in-place selectable PDF view beside the existing editor, including saved-statement editors. Extracted page text offers selected-text/whole-page copying with a keyboard fallback. Draft fields remain mounted. Scanned pages require extracted text; browser-native PDF selection cannot manufacture a text layer.

## Acceptance

Local verification: 36 unit checks and 15 Chromium journeys pass across the changed statement/recovery/duplicate flows, including 1280px and 390px views. TypeScript and scoped lint pass. Narrow coverage and group-action screenshots were inspected. Production build passes (existing large-bundle advisory remains). Live deployment remains separately gated by ongoing uploads; do not claim these changes live from a commit or build alone. Native PDF text selection also depends on the browser PDF viewer; headless Chromium can test loading and preserved editors but does not establish native selection acceptance.

Related issues: E02/E03 progress clarity, E09 repeated review, E12 duplicate handling, E14 reachable corrections, E16 read-file next actions, U01–U07 usability. Missing-month summaries cover saved usable dates only and do not establish completeness of every supplied source. Import and investigation completion remain open.

## Unknown-currency recovery

When the reader cannot identify a currency, the original PDF now stays available on that same screen. The source filename, previous/next page controls, direct page choice, zoom and native PDF copy tools let the investigator check the printed currency before continuing. Page selection is restricted to the returned source pages; switching source or statement resets the preview. Selecting a currency resumes the existing review request and does not import records.

Validation: all 62 statement-import unit tests pass, including the unknown-currency-to-review journey with non-consecutive source pages. Seven Chromium clarity journeys pass, including source navigation at 1280px and 390px; the narrow screenshot was inspected. TypeScript and scoped lint pass. Production build and release status are recorded separately below; live acceptance remains pending guarded deployment.

Unknown-currency production build passed with the existing bundle-size advisory. This result confirms local compilation only; the live source-choice screen has not yet been verified on the pending release.
