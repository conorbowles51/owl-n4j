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
> **Last synced:** 2026-06-09 19:30 UTC (by Claude)
> Feedback authors active so far: **Alex**. Logins: neil / alex / conor / arturo.

---

## A. Tester-submitted items (`user_items`)

| id | kind | title | author | reported | status |
|---|---|---|---|---|---|
| user-bug-1 | bug | Contacts in comms/timeline need phone's-perspective naming | Alex | 2026-06-09 16:03 | TRIAGED |
| user-bug-2 | bug | Make all users/accounts searchable by text (unicode) | Alex | 2026-06-09 18:50 | TRIAGED |
| user-bug-3 | bug | Comms Timeline window needs to be bigger | Alex | 2026-06-09 18:56 | TRIAGED |
| user-feature-4 | feature | Ability to export data to PDF | Alex | 2026-06-09 19:10 | TRIAGED |

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

**FAIL (Alex):**
- `tl-device-local-name` — recipient should show the name saved on the SENDING phone *(= user-bug-1)*
- `tl-time-hover` — full date & time on hover not working
- `dedup-collapse` — thread dedup/collapse not working as expected
- `media-smooth-scroll` — media scroll not smooth
- `nav-load-more-events` — "load more" events not working
- `nav-load-more-comms-files` — "load more" comms/files not working

**PASS (Alex):** tl-inline-body, tl-tz-offset, media-voice-inline, media-voice-preload,
nav-virtualized-rows, nav-sort-toggle

**No verdict yet:** tl-to-from-numbers

---

## C. Comments (`comments`)
None yet.

---

## D. Our status on the above
- All items above are **TRIAGED as of 2026-06-09** but **not yet started** (plan agreed with user this session).
- Search & Discovery rebuild shipped on branch `feat/cellebrite-search-discovery` (commit b5a75cf) — its own checklist section added to the hub (`sd-*` ids).
