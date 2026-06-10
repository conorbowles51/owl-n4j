# Testing Platform — Last Observed State

> **Purpose:** a baseline snapshot of the QA testing hub's feedback
> (`data/testing-feedback.json`) so we can tell at a glance what is **NEW**
> from testers since we last looked.
>
> **Workflow (do this every time we "check the testing app"):**
> 1. Read `data/testing-feedback.json` (the live hub data on the server).
> 2. Diff it against this file. Anything not listed here = **NEW**.
> 3. Triage new items, then update this file (add them + set a status) and
>    bump "Last synced".
>
> Status legend: `NEW` (just arrived) · `TRIAGED` (understood, planned) ·
> `IN-PROGRESS` · `FIXED` (shipped) · `WONTFIX` · `NEEDS-INFO`.
>
> **Last synced:** 2026-06-10 00:30 UTC (by Claude)
> Feedback authors active so far: **Alex**. Logins: neil / alex / conor / arturo.
>
> ⚠️ **Incident 2026-06-10:** the hub's `/api/testing/checklist` was 500ing
> (stylised-unicode/surrogate chars in a checklist string → UnicodeEncodeError),
> so the catalogue looked wiped. **Tester feedback was never lost** (all 8 items +
> 14 verdicts + 1 comment intact). Fixed (commit 797e620) + endpoints hardened
> with ensure_ascii. Lesson: keep `testing_checklist.py` strings ASCII-only.

---

## A. Tester-submitted items (`user_items`)

| id | kind | title | author | reported | status |
|---|---|---|---|---|---|
| user-bug-1 | bug | Contacts in comms/timeline need phone's-perspective naming | Alex | 2026-06-09 16:03 | FIXED (Phase 1) |
| user-bug-2 | bug | Make all users/accounts searchable by text (unicode) | Alex | 2026-06-09 18:50 | FIXED (client; backend follow-up) |
| user-bug-3 | bug | Comms Timeline window needs to be bigger | Alex | 2026-06-09 18:56 | FIXED |
| user-feature-4 | feature | Ability to export data to PDF | Alex | 2026-06-09 19:10 | FIXED |
| user-bug-5 | bug | Cannot copy/paste in Comms Timeline | Alex | 2026-06-09 19:58 | NEW |
| user-bug-6 | bug | Messages in Comms Timeline have duplicates | Alex | 2026-06-09 20:13 | NEW |
| user-bug-7 | bug | Comms Timeline doesn't load all events (scroll won't continue) | Alex | 2026-06-09 20:14 | NEW |
| user-bug-8 | bug | Comms Timeline not showing all comms already filtered (only one phone) | Alex | 2026-06-09 20:20 | NEW |

> user-bug-1..4 fixed on branch `feat/cellebrite-search-discovery` (round-2). Checklist `fix-*` items added for re-test. **user-bug-5..8 are NEW (filed 2026-06-09 ~20:00), not yet started** — all about the Comms cross-type Timeline flyover (`CommsCrossTypeTimeline`):
> - **user-bug-5** — can't select/copy text in the comms timeline.
> - **user-bug-6** — duplicate messages appear (relates to `dedup-collapse` FAIL — this is the repro I'd asked for: "some of the same messages appear multiple times").
> - **user-bug-7** — infinite scroll stops; doesn't load all events (comment: "the scroll doesn't continue scrolling").
> - **user-bug-8** — filtering by a contact shows only ONE phone's comms when multiple phones (P3, P4) have comms/calls with her — filter is dropping devices.
> New comment on user-bug-7: Alex — "Comms Timeline doesn't load all events. the scroll doesn't continue scrolling".

### user-bug-1 — phone's-perspective contact naming  *(status: TRIAGED)*
Messages out of the owner's phone show the wrong name. Isolating C5/C6 should
NOT show "Trabajo 444" as sender/beneficiary — should show how *that* phone has
the contact saved (Pefro / Mry). The system shouldn't universally label a
contact; viewing through a phone's lens should show that phone's saved names.
Proposed: per-device (device-lens) names, optionally with a universal custom
label kept alongside the device one, e.g. `Gloria Lol [Mry] (####) -> Jonathan [Flaco] (####)`.
> Ours: ties to the ContactEntry / name-conflation work (preserve exact per-device
> saved names) and the `tl-device-local-name` checklist FAIL below. Biggest item.

### user-bug-2 — make all users/accounts searchable by text  *(status: TRIAGED)*
Searching `kathia` returns nothing for `𝓚𝓪𝓽𝓱𝓲𝓪🎭`; must type the exact stylised
characters. Need unicode normalisation (NFKC fold of mathematical-alphanumeric
letters → ASCII, strip emoji/zero-width) on BOTH the query and the haystack.
> Ours: directly extends the new Search & Discovery fold (diacritics only today).
> Quick win; also applies to Comms/Contacts search.

### user-bug-3 — Comms Timeline window too small  *(status: TRIAGED)*
The Comms cross-type Timeline is constrained to a small window; enlarging it
still shows a small window with a white gap below. Layout/height bug in
`CommsCrossTypeTimeline` / its container.

### user-feature-4 — export to PDF  *(status: TRIAGED)*
Export filtered data to PDF — e.g. comms between 2 people within a date range,
either just the conversation or the timeline of all comms between the selected
people.

---

## B. Checklist status feedback (`items`) — fails are bugs to triage

**FAIL (Alex) — triage outcome:**
- `tl-device-local-name` — **FIXED** (same as user-bug-1; device-lens names now in timeline/comms/calls/emails)
- `tl-time-hover` — **FIXED** (Events table time cell was missing the tooltip; Timeline already had it)
- `dedup-collapse` — **NEEDS-INFO** (code review found dedup working; only a rare empty-participant edge case. Need a concrete repro/screenshot of the duplicate seen)
- `media-smooth-scroll` — **FIXED** (explicit image dimensions + lazy audio preload; thread-list virtualization is a larger follow-up if still janky)
- `nav-load-more-events` — **WORKS / partial** (Timeline load-more works; Event Center intentionally caps at 5000 with a truncation banner — adding a load-more there is a follow-up)
- `nav-load-more-comms-files` — **WORKS** (Comms thread load-more + Files offset paging both verified working in code; likely tester confusion — re-check, and tell us the exact view if still failing)

**PASS (Alex):** tl-inline-body, tl-tz-offset, media-voice-inline, media-voice-preload,
nav-virtualized-rows, nav-sort-toggle

**No verdict yet:** tl-to-from-numbers

---

## C. Comments (`comments`)
None yet.

---

## D. Our status on the above (updated 2026-06-09 20:30)
Round-2 fixes shipped on branch `feat/cellebrite-search-discovery` (stacked on the S&D rebuild). Backend restarted; frontend live via HMR. Per item:
- **user-bug-1 / tl-device-local-name** — FIXED. `_project_call/message/email` + `get_event_related` + `get_cellebrite_thread_detail` (calls/emails) now resolve the counterparty through `device_contact_names` (the name the VIEWING report saved them under). Verified in-process: 17/17 sampled message counterparts match the device-lens map; 213 numbers carry >1 distinct per-device name. **Phase 2 (universal label alongside device name) NOT done** — separate ask.
- **user-bug-2** — FIXED for client-side filters (`utils/cellebriteSearch.js` `normForSearch`: NFKC + diacritics + emoji/zero-width strip on both query and haystack). Verified 𝓚𝓪𝓽𝓱𝓲𝓪🎭→kathia. **Backend Search & Discovery vs stylised STORED names NOT fixed** (Cypher can't NFKC; needs a normalised shadow field + backfill) — follow-up.
- **user-bug-3** — FIXED. `CommsCrossTypeTimeline` root `33vh`→`100%` so the flyover fills its panel.
- **user-feature-4** — FIXED. New `comms_export_service.py` + `/api/cellebrite/comms/export/pdf` (reuses WeasyPrint `render_pdf`) + Timeline/Conversation PDF buttons in the Comms Center. Verified valid PDFs both modes; capped at 2000 items (~20s worst case for the single busiest participant; typical filtered export is fast).
- **tl-time-hover** — FIXED (`EventsTable` time cell `title`).
- **media-smooth-scroll** — FIXED (image width/height + `aspect-ratio`, audio `preload="none"`).
- **dedup-collapse** — NEEDS-INFO (no clear bug found; awaiting repro).
- **nav-load-more-*** — WORKS in code (Timeline/Comms/Files); Event Center load-more is a follow-up.

Search & Discovery rebuild itself: commit b5a75cf, checklist `disc-*` ids.
