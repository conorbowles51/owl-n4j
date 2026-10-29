# 6. v1 phone screens: inventory, feedback trajectory, overlap

Read-only, 2026-10-29, `origin/main`. Per Neil, all committed v1 work was directed with Alex from her use of
the platform, so commit volume per screen is used as that signal. Quotes come only from written sources:
`.claude/plans/*` on `origin/main`, commit bodies, v1-era memory notes (copied from
`/root/.claude/projects/-home-conorbowles51-app-v2/memory/` on the VM), the call notes in the working tree,
and Alex's own testing-hub entries (`/home/conorbowles51/app_v2/data/testing-feedback.json`, 9 and 10 June
2026; titles and verdicts listed in spec 03 section 17.0). Case content is removed: a quoted customer ask
that contained a real phone number and saved contact names is shown with those replaced.

## 1. Screen inventory

Tabs defined at `CellebriteView.jsx:27-51`.

| Tab | What an investigator can do | Main endpoints | Lines | First / last commit | Commits |
|---|---|---|---|---|---|
| Overview | Per-device drill tables (contacts, calls, messages, emails, locations with map and trajectory); delete or rename a report; "Filter Comms"; merge identities | `/overview/*`, `/persons/merge`, `/reports/{k}` | 601 (+~1,800) | 36176f33 04-06 / 80bc7a3d 05-24 | 7 |
| Report | Per-device profile: inferred owner with an amber flag when another person dominates; summary cards; callouts; client PDF | `/report/devices`, `/callouts` | 275 | 1a323b6e 05-27 / 87ae0858 06-08 | 3 |
| Search & Discovery | One search across phones grouped People, Messages, Locations, Other, Files; pivots to tabs or graph | `/discovery/search` | 403 | b6f5023e 06-09 | 1 |
| Comms Center | Thread list and reader; participants filter (From/To split or Any); app, type, attachment filters; full-text search; envelope scrubber; cross-type timeline flyover with swim lanes | `/comms/*` | 1,320 (+~4,500) | 3fcbbea8 04-24 / 1ee78cf4 07-04 | 37 |
| Contacts (unified) | Roll-up by E.164 number with every alias across phones; per-device breakdown; merge identities | `/contacts/unified` | 277 | 4bc74f7f 05-14 / 06f10d0b 05-27 | 3 |
| Locations | Server-side tile clusters; points and devices per tile; trajectory with arrows; playback; `place:` and `near:` search; phone by day table | `/locations/*`, `/events`, `/events/tracks` | 879 (+708) | cad63fd6 05-13 / 71c1a1b6 06-30 | 19 |
| Location & Events | Map, split and table of every event type; playback; event timeline; five-method intersections (`IntersectionPanel.jsx:5`) | `/events*`, `/intersections/run` | 706 (+~2,600) | 3fcbbea8 04-24 / 71c1a1b6 06-30 | 17 |
| Files | Tree, list, detail; tags, entity link, bulk actions; EXIF-date and geotag filters; on-demand transcription and image recognition | `/files`, `/files/tree` | 387 (+~1,460) | d0183dbb 04-24 / 639372b9 06-05 | 5 |
| Cross-Phone Graph | Person and resource graph with 14 edge toggles; server search rebuilding the subgraph; flow view; time axis; comms between a pair; event stream; shortest path; add node | `/cross-phone-graph*`, `/comms/between` | 2,695 (+876) | 36176f33 04-06 / a930d1b5 06-08 | 32 |
| Timeline | Chronological feed of every event type; sort; zone-aware day groups; inline body, thumbnails, voice notes; load more; callouts; swim lanes with cross-phone arcs | `/events*`, `/callouts` | 1,102 (+777) | 36176f33 04-06 / 8d3aeb33 06-30 | 27 |
| Communications | Contact-frequency table; shared-contacts panel; breadcrumb drill into a per-contact feed; pushes the perspective to other tabs | `/communication-network`, `/comms/contact-feed/{k}` | 512 (+821) | 36176f33 04-06 / 9c2fd9c3 05-27 | 6 |

Shared shell: selection rail (`shared/rail/*`, ~2,000 lines), status bar, zone selector, scrubber,
`useTimelineWindow`. Dead code: `comms/CommsContactDrawer.jsx`, `CommsDeviceSelector.jsx`,
`CommsEntityFilter.jsx` (no importer); `/cellebrite/timeline` and `/comms/attachment/{id}` (no caller).

## 2. Feedback trajectory by theme

**A. Completeness ("is this all of it?")**
- 05-06: timeline silently dropped events. "Confirmed by user 2026-05-06 … investigators were drawing
  conclusions from incomplete data" (memory `feedback_no_silent_truncation.md`). Built aeb3e598, 477685b5,
  c7809469, c764f03c, ab4fc5f0. Later caps removed or made visible: d4ec444b, 5bca0a84, 09bd9a8c, dc5103e1,
  639372b9, 8c45053a.
- Testing hub (Alex): "Comms Center not displaying all calls … The Comms center only shows 1 call when
  filtered"; "Comms timeline is not showing all comms already filtered"; "Comms Timeline doesn't load all
  events. the scroll doesn't continue scrolling"; load-more under filters "honestly this slows down the
  investigator … when filters are at play, the timeline should load in full." DKT-42 took three attempts
  (fcb611e7, c0c1c90e, 5b854590); DKT-29 unknown error after filtering (03b04f23); DKT-23 duplicates
  (330ef1fe, 3cf58bfb).

**B. Who is this person (17+ commits)**
- Customer ask recorded verbatim in `cellebrite-comms-geo-deep-dive.md:389-395`: if everyone is texting one
  number, show all messages by that number, with every name it is saved under on each phone [number and five
  saved names removed]. Built: Unified Contacts 4bc74f7f.
- "User flagged (2026-05-27)" numbers missing beside names (memory `feedback_cellebrite_number_alongside_name.md`).
  Built b51604d7, 1a323b6e, 9c2fd9c3.
- "Perspective is primary" (memory `feedback_cellebrite_perspective_primary.md`, 2026-06-10): the case-wide
  roll-up must be opt-in. Testing hub (Alex): "if I'm looking through a phone's lens, then I want to see how
  that phone views the world." Built 06f10d0b, 7d6f31cb.
- Same person under several numbers: manual audited merge (72dfa276, daff34a7, ac75970a).
- Owner attribution: "phones get processed without a phone number. This should NEVER happen" (memory
  `feedback_cellebrite_phone_number_required.md`); "Alex's 'unknown' symptom" (memory
  `project_cellebrite_owner_number_inference.md`). Built 35fe75a5, f4cae847, 0da927ea, fd82ea77.
- Roadmap handwritten note: "recipient should render as the contact name as saved on that device. Show
  both phone numbers" (`alex-call-roadmap.md:17`). Testing hub (Alex): "it should show as: [name] (#####) ->
  [name] (####)". Built 7d6f31cb, 45b464f8.

**C. When (time zones, date filters)**
- "Two overlapping timelines … the day appeared to end at 8 PM" (55d82be1; memory
  `project_cellebrite_timestamps_utc.md`).
- Roadmap: "Filter to selected timezone", "full date + time" (`alex-call-roadmap.md:18`). Testing hub
  (Alex): "only shows time. not the day … military time which is confusing. can we do 12h?" Built 45b464f8,
  bc76d6be.
- DKT-40 filtered dates wrong: first PR reverted (a05950cd), superseded by 71c1a1b6 applied to "all 5
  timelines", plus 81520e02.
- Seconds-level ordering agreed in the 2026-07-10 call notes; no v1 commit (work had stopped).

**D. Reading conversations at scale (most iteration)**
- "Scrubber added but cumbersome", "infinite scroll still frustrating", "Avoid symbols like slashes in
  search queries" (`deep-dive.md:60-64`); "very hard to work in the messaging row even with the Conversation
  timeline minimized" (`:499`; built 83373e3a).
- K-redesign 21883589; removing the bottom timeline "lost a feature investigators rely on" (45681410);
  "User preferred the original From/To split" (K1 reverted, 96db22cc).
- Testing hub (Alex): "Comms Timeline Window Needs to be Bigger" (38f48a2f); copy/paste broken in comms and
  timeline (fix applied to both swim-lane files, d7f4f005); duplicates.

**E. Where were they (28 commits by keyword)**: "Location/address search if data exists", "Test cross-device
overlap detection" (`deep-dive.md:70-71`). Built cad63fd6 to 85504150, 1271c17e, cc008f90, 5a6964dd and about
15 typeahead and trajectory commits on 05-17.

**F. Who talked to whom (28 to 32 commits)**: "directionality of messages & calls. Bugs: search not
rebuilding graph, selected not showing, filters not working" (`alex-call-roadmap.md:20`); "The user
(correctly) said it didn't have to be about shared things — just show the data" (919bef5b). Built S2-13 to
S2-20, 49105bcc to a930d1b5.

**G. Deliverables**: roadmap Sprint 3 entity summaries, callouts, PDF (d18eea77, 63608486, 87ae0858).
Testing hub (Alex): "Ability to Export Data to PDF" of a filtered conversation or timeline; the timeline PDF
cut message text, shifted a date by a day, and printed decorative letters as squares.

**H. Context around an event**: "Clicking a Telegram message or a phone call … should surface … Conversation
thread … Around this time" (`deep-dive.md:344-346`; built 903b9a28); the always-on rail became a flyout
(7c4d5f75).

**Iteration ranking:** Comms Center (37 commits, 5 DKT tickets, one design reverted, three failed fix
attempts); Cross-Phone Graph (32); Timeline (27 plus swim lane); completeness and caps across all of them.

## 3. Overlap and redundancy

1. **Comms Center vs Communications vs Overview drill tables**: "every comm with person X" three ways via
   three endpoints (`/comms/between`, `/comms/contact-feed`, `/overview/*`). Unique to Communications: the
   multi-hop drill and perspective push; unique to Comms Center: threads, full-text search, scrubber.
2. **Timeline vs Location & Events vs Locations vs Overview > Locations**: all read `/events` or share
   `EventMapPanel`; trajectory and playback exist twice; Location & Events' list duplicates Timeline. Unique to
   Location & Events: the intersection engine (1 to 2 commits, no feedback). 71c1a1b6 had to patch five
   timeline hosts.
3. **Two swim lanes** (`CellebriteTimelineSwimLane.jsx` 777 lines, `comms/CommsCrossTypeSwimLane.jsx` 745):
   same lanes, arcs and selection; both fixed for DKT-28.
4. **People across four or five tabs**: Unified Contacts, Communications' shared contacts, Overview contacts,
   graph persons, Discovery People; merge reachable from two places.
5. **Search**: Discovery composes the same searches as Comms full-text and graph search (b6f5023e).

Low-signal screens: Discovery (1), Report (3), Unified Contacts (3, but with a verbatim origin ask),
Communications (6), Files (5), intersection panel.

## 4. Requested but not built, or reverted

Reverted: DKT-40 PR #102 (a05950cd); DKT-43 comms tally (f75fe572, 1ee78cf4; four attempts per memory
`project_dkt43_comms_tally.md`); K1 combined participants filter (96db22cc); K4 bottom-timeline removal
(45681410); persistent rail to flyout (7c4d5f75).

Not on `origin/main`: S2-22/23 comms multi-select and combined filters; S2-24/27 create node in tables; S2-21
flow over time (partly via 3828e411); S1-08/09 working-zone filter; S1-10 owner as "You"; S3-10; Watch List;
geofence intersection; cell-tower triangulation; "ingest XML only, link files later"; off-thread parsing;
"show deleted only" (`deep-dive.md:282`); RFC-822 email threading (parked, `:578`); natural-language spatial
and time search (parked, `:615-619`); cross-identity "Link identities" toggle; seconds-level timestamps; a
Discovery date window and separate Calls and Emails groups; strict-join call threads (memory
`project_cellebrite_call_one_edge.md`).

## 5. Assessment (inference)

Highest value: Comms Center, Timeline, Cross-Phone Graph. Cross-cutting rules that carry more weight than
any one screen: a name always with its number; truncation never silent; the phone's own perspective by
default. Merge or repurpose: Communications into Comms Center or Unified Contacts; Location & Events into
Locations plus Timeline, keeping intersections as a fixed feature; one swim-lane component; one identity
surface; Discovery as the search entry point; delete dead code. Overview and Report could become one
per-device profile. The plan's section 10.5 and spec 03 section 16 adopt this.
