# Loupe — Development Timesheet Summary

**Period covered:** 5 – 26 July 2026
**Repository / branch:** `owl-n4j` — `integration/evidence-main-reunion`
**Days claimed:** 7
**Basis:** 28 committed changes, cross-referenced to the Docket ticket board (tickets DKT-687/688/689, DKT-807, DKT-920, DKT-934, DKT-938–943 and the case-authorization work under Epic 19)

---

## Day 1 — Investigator edits, case notebook and saved timelines

*Work dates: 5 July*

Built the ability for investigators to correct and add to a case themselves rather than only viewing what the system extracted: entities and relationships can now be created and edited by hand, with the change recorded against the person who made it. Added a case notebook so investigators can capture their own working notes alongside the evidence, and introduced saved timeline views — an investigator can build a filtered view of events, name it, save it, and come back to it later or export it for use outside the platform. This touched roughly 60 files across the interface, the backend and the database, and included new automated tests for each of the three areas.

## Day 2 — Smarter document summaries and admin platform controls

*Work dates: 5 – 8 July*

Improved the automatic document summaries so the system takes into account what kind of folder a document sits in — a bank statement folder and a witness statement folder now produce appropriately different summaries instead of one generic treatment. Separately, built the administration controls that let an administrator see the platform's current version and apply updates from inside the app, rather than needing someone technical on the server. Both were delivered with test coverage, and the admin surface includes status reporting so an update in progress is visible rather than silent.

## Day 3 — Loupe rebrand across the product and release stability

*Work dates: 12 – 15 July*

Rolled the new Loupe identity through the whole application — colours, typography, logos, icons and the shared design system — covering over 100 screens and components so the product is consistently branded rather than partially renamed. Alongside this, fixed two problems that were blocking reliable releases: the timeline screen was failing to load consistently, and the deployed environment was serving an outdated version of the interface instead of the freshly built one. This is the work that made the branded build usable by others rather than only on a developer machine.

## Day 4 — Case access control and location accuracy

*Work dates: 17 – 19 July*

Closed a significant security gap: every application programming interface now verifies that the person calling it is actually a member of the case they are asking about, so a user cannot reach another case's data by guessing an address. This was delivered with an automated test suite that checks each route family, so the protection cannot silently regress. The same period covered location accuracy at intake (DKT-934) — the system now records how specific an extracted location actually is (a full street address versus just a city or country) instead of treating every mention as equally precise, which is what allows the map to be honest about confidence.

## Day 5 — The Significant layer, case-wide search and graph improvements

*Work dates: 19 – 23 July*

Delivered the "Significant" feature (DKT-688, DKT-689): an investigator can mark any piece of text or any entity as significant to the case, and that marking then shows up consistently everywhere — on the network graph, on the timeline and in the table view — giving a single case-wide view of what matters rather than notes scattered per screen. Added case-wide plain-text search across every document in a case (DKT-687), so an investigator can find a name or phrase across the whole evidence set in one query. Also added a toggleable 3D view of the case network graph (DKT-940) and fixed entity merging so that when two records are combined, the record of where each fact originally came from is preserved rather than lost.

## Day 6 — Scanned documents, ingestion reliability and AI provider settings

*Work dates: 21 – 23 July*

Built automatic text recognition for scanned PDFs (DKT-938), so documents that are effectively photographs of paper are now readable and searchable like any other document — previously they entered the case as blank. Made that process resilient to timeouts so a single slow document no longer stalls an entire batch. Centralised the AI provider configuration into one settings screen (DKT-807), so which AI provider and model the platform uses is an administrator choice made in the interface, with credentials stored properly, rather than something hard-wired into the code. Also fixed two visible defects: overly verbose document summaries (DKT-941) and evidence that stayed stuck showing an old status after being reprocessed (DKT-942).

## Day 7 — Speaker-separated audio transcripts and the Loupe landing site

*Work dates: 25 – 26 July*

Delivered diarized audio transcription (DKT-939): audio evidence is now transcribed with each speaker separated out, and the investigator can review the transcript, label who each speaker is, and merge speakers the system split incorrectly — turning a wall of unattributed text into an attributable record of who said what. Finished with a full rebuild of the public Loupe landing page and brand system (DKT-920), including the new visual identity and interactive hero, which is the front door for prospective customers.
