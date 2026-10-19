# Findings and Observations: compact cards and readable saved text

The 24 September follow-up supersedes the earlier full-width compact rows. The
investigator needs to scan saved work and reach Edit or Add to Timeline without
searching the far edge of a wide screen.

## Investigator journey

1. Open Financial → Findings & Observations. Collapsed records appear as compact
   square cards beside each other, with one column on narrow screens. Card width
   is capped; long titles may grow the card rather than hide text or controls.
2. Read the title, type/progress, supporting-payment count and author/date. Edit
   and Add to Timeline sit directly below the title. Include in report remains
   available on the collapsed card. Read-only users can review the same records
   without mutation controls.
3. Select the title to expand. The selected card uses the available grid width
   for the complete explanation, linked evidence and report actions. Its title
   and primary actions remain together. Selecting the title again restores its
   compact card; the control stays in view.
4. Edit opens the existing editor for this record, preserving its source links
   and optimistic version check. Save and return refresh the card. Add to
   Timeline opens the existing date/preview/confirmation journey for this record.
5. Search, type/progress filters, page, expanded records and report selections
   retain their existing case/user-scoped behavior when navigating away and back.
   Failed loading can be retried without losing the current search/page.

## Saved text compatibility

The structured note parser previously required a newline after the final
`Assigned to` heading. Existing saved records whose trailing newline was trimmed
could therefore expose the storage headings inside the explanation, particularly
when follow-up fields were empty. The reader now accepts that stored form and
Windows newlines. Empty follow-up sections are omitted; populated next actions
and owners remain separate labelled content and reopen in their correct fields.
Escaped literal section headings still round-trip through editing.

Narratives use the existing safe Markdown renderer for actual headings, lists,
emphasis and links, including older unstructured notes and saved analyses. Raw
HTML is not enabled. Viewing does not rewrite saved text, source records,
transaction values or historical reports. No migration or recovery job is needed.

## Verification

- 16 focused unit tests pass: saved-work navigation, report selection, retry,
  formatted existing text and empty/trimmed/Windows-newline follow-up parsing,
  including literal headings retained through editing.
- Six Chromium journeys pass: square-card geometry and action placement at
  1360×900; expansion/collapse, retained selection and return; 420-pixel viewport
  without horizontal overflow; Edit from a collapsed card, save and reopen;
  Finding/Observation → explicit event date → Timeline → source → return;
  duplicate prevention and recovery after a stale Timeline preview.
- Desktop, narrow and expanded screenshots were visually inspected. The browser
  uses synthetic API fixtures and the actual components/dialogs. The editor
  fixture trims saved text and advances its version, reproducing the older note
  shape without a client-data write.
- Scoped ESLint, TypeScript/production build and diff whitespace checks pass.
  The financial action inventory was regenerated (1,667 actions, 173 components).

This is a frontend-only release. No worker, job, schema or case-data changes are
required. Push is the existing automatic deployment trigger. The previous
live-origin access restriction remains in place, so independent live verification
is not claimed. Test screenshots and all client documents remain outside Git.
