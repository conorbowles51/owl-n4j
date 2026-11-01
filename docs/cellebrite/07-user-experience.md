# Cellebrite rebuild, spec 07: user experience

This spec owns the investigator journeys, the interaction rules shared by every phone screen, how phone material is collected into Loupe's existing case-building system, how phones work with the rest of Loupe and on their own, and how usability is measured and gated. Rules for one screen live in the spec that owns that screen. This spec lists those edits in the spec-change table that cb-ground applies (section 15) and names the tests. Specs 01 to 06 are cited by section.

**Names.** "01" to "06" are the phone specs: 01 intake, capture and storage; 02 interpretation, identity and projections; 03 screens; 04 pattern of life; 05 investigative approaches; 06 build order. Research notes are `docs/cellebrite/research/01` to `09`. Note 09 holds the user-experience and methods sources, including every named product.

**Numbers.** Numbers inside quoted screen copy are illustrative unless they are marked *measured* with a source. Thresholds that have no source are recorded as decisions, each with what reverses it (section 16), or are labelled **estimate, not measured**.

**Jobs.**

| Job | What it builds | Starts |
|---|---|---|
| cb-ground | Spec corrections and measurements, plus the spec text this spec asks for | running |
| cb-ux | Shared phone interface kit, fixture extension, prototype, instrumentation, guide, session packs | now |
| lx-collect | Changes to Loupe's existing case-building system that phone collection needs | now |
| cb-capture | Intake | cb-ground DONE |
| cb-interpret | Interpretation, identity, the review of judgement calls | cb-capture DONE |
| cb-screens | Phone screens and phone layers on shared screens | cb-interpret DONE |
| cb-pol | Pattern of life, Statement check, the shared Lanes component | cb-interpret DONE |
| cb-crossev | Phones beside the ledger; agent phone tools; graph communication edges | cb-screens DONE |
| cb-approaches | The investigative approaches | cb-crossev and cb-pol DONE |
| cb-media | Media derivation: transcription, text read from images | cb-screens DONE |
| lx-corrections | The shared feed that records every manual change or confirmation | running |
| followups | Loupe-wide items outside the phone build | running |

**Terms.**
- A **record** is one item read from a phone report.
- A **reading** is the system's interpretation of a record, for example which field is the sender.
- A **judgement call** is a reading the system has applied that no person has confirmed.
- To **collect** is to put phone material into Loupe's existing case-building system: dossiers (Loupe's profiles of people, places, devices, organisations, vehicles and events), Workspace notes, findings and theories, tasks, Timeline curation and saved views, and Significant. In the interface the menu is labelled **Add to…**

---

## 1. The gap this spec closes

Counted over the plan and 01 to 06 on the release branch:

- "usability", "UX", "user experience", "onboarding", "usability test", "task time", "time left" and "time remaining" each occur 0 times. "workflow" occurs once, as a heading in 02 6.8. "help" and "guide" occur 0 times in 03.
- 03 has 1,747 lines. About 306 are common rules (3.1 to 3.11) and about 227 describe layout and interaction per screen (approximate, from section spans). No section covers the export dialog, the list for each record type, the judgement-call review screen, the Pattern of life screen or the approach results.
- 03 names 65 tests. About 12 exercise interaction mechanics. 0 are multi-step investigator tasks and 0 time a person. A15 is the only layout test. The capture, screens and pattern-of-life finish lines are signed-in screenshots, which prove that a screen renders, not that it can be used.
- 9 of the 16 phone decisions in 02 8.8 have no control on any screen: device zone, applying a zone to times with no offset, default region, clock offset, value correction, identity label, phone label, external processing, and accepting a reconciliation difference. Setting the owner appears only as a label, and an unset owner blocks every person-level pattern-of-life view. The intake message says "Use Replace", and no screen has Replace. The approaches, the Pattern of life screen and the incident window have no route or menu entry.
- The ruling "Map messages and calls but flag as needing a judgement call from the user" appears in 0 spec documents. The financial review queue built on the same idea holds 1,823 calls: 1,820 open, 2 confirmed, 1 corrected (*measured*, lx-corrections).
- The waiting standard is not met. Loading reads "skeleton rows plus Counting matching messages". Export progress is a number from 0 to 1 with no words. Intake updates "at most once per second" and gives no time left. Interpretation has no visible state.
- Collecting is nearly absent. "Add to Workspace" exists only on conversation rows and media detail. It is built at 06 row 31, before its link type arrives at row 50. Dossiers, interviews, the Notebook, Timeline curation, tasks and the financial report cannot hold a phone record.
- The rest of Loupe does not see phones. The agent has no phone tool, no phones-only case is specified, and the Timeline lens and Map layer default to off, so a phones-only case opens both screens empty.
- 03 contradicts itself in several places. They are listed in section 15.

**What stays:** complete results under filters; name and number on every line; the phone's own names by default; the day plus 12-hour time with the zone; the record behind every line; visible duplicates; exact state wording; masked sensitive fields; reversible decisions under a person's name. Each comes from something Alex filed, and each has a test.

The financial screens show what happens without this layer. Every screen passed its checks, and the whole was rejected: "please design this from an investigators perspective". What worked was one complete journey with a way back. This spec gives the phone piece that layer before its screens are built.

---

## 2. Users and their jobs

| User | What they are trying to get done | Output they need | Basis |
|---|---|---|---|
| Alex, lead investigator | Narrow to one person's phones. Filter by a person, by name and by number. Compare what each phone holds about that person. See who wrote to whom on every line. Read whole results under filters. | A PDF of "comms between 2 people and between x dates ... either just the conversation or the timeline of all comms between the people selected". Text to copy into reports. | Testing hub, 9 and 10 June |
| Alex's team | Share the reading of large phones: up to 186,787 messages in 4,491 chats on one phone, and 7,584 chats in one case (*measured*). Know what has been read and what is left. Hand work over. | Findings, dossiers and a chronology that cite records | Scale measured. Team size and how work is split are **assumed**. |
| Case owner (an analyst or Neil) | Set the case up: zone, region, whether phone material may reach the AI service. Confirm or correct readings. | Readings that are confirmed, or visibly unconfirmed | cb-interpret brief |
| New team member | Learn terms such as "Recovered by carving" and "not yet confirmed" without misreading evidence | Confidence that what they read is complete | **Assumed** |
| Counsel and court (outside the app) | Read exhibits and understand how a finding was reached | Full text; day, 12-hour time and zone; every character drawn; the filter stated; record ids; the reading state of every row; a record of what was examined | **Assumed** from the export requests |

**Alex's words** (structure only):
- "if I'm looking through a phone's lens, then I want to see how that phone views the world"
- "it should show as: [name] (#####) -> [name] (####)"
- "having to click load more constantly is pretty annoying ... when filters are at play, the timeline should load in full"
- "only shows time. not the day ... military time which is confusing. can we do 12h?"
- the proposed label "[case label] [phone's name] (#####)"

**Facts that shape the design:**
- Alex calls phones by short labels ("C5 and C6"). Two reports in one case can share a label, so every picker shows the label with the extraction date.
- Alex's entries cover the first 20 of 63 checklist items, and he did not understand one prompt about UTC offsets. Test packs are short, task-based and plain, and understanding is tested directly (section 10.3).
- Alex asked for "Load more" and then called it "pretty annoying" after using it. Stated wishes change with use, so prototypes are tried with people before screens are fixed, where sessions can be held.
- Two earlier redesigns were reverted against investigator preference: the combined From/To picker, and the removal of the bottom conversation timeline.
- **Assumed:** laptop screens about 1280 px wide (the financial fixes were measured at 1280×720 and 1440×900), long reading sessions, and work at plain `http://104.196.62.215:5174`.

**The jobs, in the investigators' terms:**
1. Triage a new phone.
2. Who talked to whom, when, on which app, and what was said.
3. What happened around a moment.
4. Where was the phone, and were two people together.
5. Does a statement fit the phones.
6. Whose phone is this, and who is this number.
7. Follow the money beside the communications.
8. Build the case (dossiers, findings, theories, chronology) with sources kept.
9. Share the review, pick it up again, hand it over.
10. Produce the exhibit, explain how it was found, and record what was examined.

---

## 3. Journeys

Every journey has a scripted browser test with the same id. Targets are **targets, to be measured**. Methods:
- **[S]** a scripted browser test on the http address, signed in
- **[I]** in-app instrumentation, counts and timings only
- **[M]** a moderated session

Human active time is reported separately from processing wait. Only [S] and [I] results gate a job (section 11). [M] results feed follow-up work.

Each journey states **Testable from**: the unit that completes its last dependency, and the job gate that carries it. Where a journey spans jobs it is split into lettered parts.

### J-1 Add a phone and know it arrived whole

- **Goal:** get a report into the case and know what arrived, what is missing and what needs a decision.
- **Start:** Evidence, then "Add phone report (folder or ZIP)". No vendor name appears on the button.
- **Steps:**
  1. Pick a folder. Within 2 s: "Checking files before upload: 12,400 of 43,144, about 3 min left", updated every second. Browser hashing speed is measured on a synthetic folder of the same shape before any time-left figure is shown.
  2. Upload: "Sending 2.1 of 6.4 GB, about 9 min left. If this tab closes, choose the same folder again to continue."
  3. One "Getting C3 ready" card lists every stage in words, with true counts and time left: Checking the report; Reading records; Checking nothing is missing; Reading messages and calls; Building case views; Making it searchable; Making thumbnails. The same card appears in the case attention feed, so the person can leave the page.
  4. When Conversations is usable, the card says "Conversations are ready. Thumbnails are still being made (4,200 of 43,043). Open the phone summary."
  5. The Phone summary opens with its verdict line (J-2).
- **Saves:** nothing is collected. Owner, zone and replacement go through the decision log and the corrections feed.
- **Targets:** no screen goes more than 2 s without words [S, I]; at most 3 human actions [S]; participants say correctly whether the phone is complete [M]. Time to ready is measured per stage on the first three real phones before any target is set. 01's "30 min for the largest phone" stays an **estimate, not measured**.
- **Failure states:**
  - Reconciliation difference: "Held: the report lists 1,204 call records; 1,198 were read. See which." The choices are **Accept the difference** (typed reason) and **Keep held**.
  - Same phone already in the case: "This looks like a newer report of C3 (extracted [date]). Replace the older one / Keep both." Both work.
  - Protected single-file report: "A copy without a password is needed from whoever produced it." This creates a Workspace task.
  - No owner number found: capture completes. The Phone summary shows a non-blocking prompt, "No owner number was found. Set the owner", which writes `set_phone_owner`. Intake has no owner field (03 7.3, 02 8.6).
  - Stalls follow the rule in 4.7. Try again appears only when the server reports that the step stopped.
  - A failure names the step and gives a reference id and Retry. "Unknown error" never appears. Cancel sits on the card and says what is kept.
- **Testable from:** J-1a (pick, hash, send, and the stages through "Checking nothing is missing") in the cb-capture gate. J-1b (the remaining stages through the Phone summary) in the cb-screens gate.

### J-2 First look at a phone (triage)

- **Goal:** decide whether the phone is worth time and where to start.
- **Start:** the Phone summary (the screen 03 calls "Extraction profile").
- **Steps:**
  1. Verdict line: "Read in full: 338,715 records, [first date] to [last date], 6 apps. 2 apps could not be decoded. 3 things need a decision."
  2. A **Needs a decision** box with each control in place: owner, zone, times with no offset, region, label, readings to check, reconciliation.
  3. A triage block. Every number links to the matching filtered screen.
     - coverage bands by month, with "No data" kept apart from quiet periods
     - the top 10 people by contact, with name, number, and message and call counts
     - busiest weeks and apps
     - deleted and recovered counts
     - files missing
  4. **Where to start**: suggestions computed from counts and labelled as suggestions.
- **Saves:** link the owner to a person dossier; add the phone to a device dossier.
- **Targets:**
  - Whose phone it is, the period covered, the top 5 people, what is missing and where to start, answered in 3 min or less [M].
  - First data within 1 s and the page complete within 5 s on the largest phone [S].
  - Every number equals the count on its linked screen [S].
- **Failure states:**
  - Owner unknown: "No owner number was found. Person-level views stay off until an owner is set. Set the owner."
  - Zone unknown: "This phone did not record its time zone. Times show in the case zone (Eastern time). Change", which links to Case settings.
  - Still reading: "(so far)" appears beside every count.
- **Testable from:** 03-4, in the cb-screens gate.

### J-3 Everything with one person, or between two, across apps and phones

- **Start:** a dossier's "On the phones" panel, Conversations People mode, a search hit, the Phone summary's top people, or a scope preset (4.5). A Graph node or edge is a further start once graph communication edges exist.
- **Steps:**
  1. Pick A. The scope bar reads "A (3 numbers, 2 accounts) on 4 of 14 phones".
  2. Choose **Between A and B**, **Sent by A**, **Sent to A** or **Involving A**.
  3. "Include this person's other numbers and accounts" is off by default, and its effect is always shown: "Include 2 more numbers (+412 messages)".
  4. **All channels** merges SMS, calls and apps into one stream, with an app and phone chip on each row: "2,140 messages and 96 calls between A and B on 3 phones".
  5. Read with j/k. `r` opens the record panel. Mark the thread reviewed.
- **Saves:** select rows, then **Add to…** (`c`): dossier, finding or theory, note, Timeline, label. "Save this view" stores the scope as a Workspace note (section 6).
- **Targets:**
  - From a person's name to the full two-person result between two dates in 45 s or less and 6 actions or fewer [M, S].
  - First rows within 1 s of the last filter change on the largest phone [S].
  - Counts equal the dossier panel [S], and the Graph edge once it exists [S].
- **Failure states:**
  - Identities only suggested: "2 more numbers may be A. Review the suggestions." Nothing is merged silently.
  - A phone still being read: "C8 is still being read (62%). Results are incomplete until it finishes."
  - Window failed: an inline retry row with a reference id; the total stays.
  - Newer data: "Newer data is available. Refresh keeps your place."
  - Unconfirmed readings: "41,233 of these messages use readings not yet confirmed. Check them."
- **Testable from:** J-3a (all starts except Graph) in the cb-screens gate. J-3b (Graph start) in the cb-crossev gate, because graph communication edges (03-11) depend on 02-U16 in stage G.

### J-4 Read a conversation around a date

- **Steps:**
  1. A time strip under the stream shows message density for the scope. It is resizable (48 px by default) and collapsible.
  2. Click a day, or use **Go to date** (`g`). The stream lands on that day. The day header names the day and the zone: "Tuesday 4 March, Eastern time (UTC-5)". **Previous day** and **Next day** buttons sit in the day header, with Alt+K and Alt+J.
  3. `a` opens **Around this time** inside the record panel. It shows the same people on other apps and phones within a chosen window (30 min, 1 h, 24 h), the nearest positioned records within an hour, and same-day case events and payments worded "same day". Every group is counted.
- **Saves:** select a range with Shift+click or Shift+J/K, then **Add to…**
- **Targets:**
  - From an open thread to the first message of a chosen date in 30 s or less and 4 actions or fewer [S, M].
  - Context opens in 2 actions or fewer and 1.5 s or less, and closing it leaves focus and scroll anchor unchanged [S].
- **Failure states:**
  - "No messages on 12 March in this thread. Nearest: 10 March (14) and 15 March (3)."
  - "6,894 messages have no time and are listed at the end."
  - "No data" bands are never shown as no activity.
- **Testable from:** 03-3, in the cb-screens gate. The "same-day payments" group is tested in cb-crossev.

### J-5 Reconstruct the window around a moment, across phones

- **Start:** "Open the window around this" from a record, a key date or Timeline Lanes. Later starts: a ledger payment, a statement claim, the incident window.
- **Steps:**
  1. One Lanes view: one lane per phone, a Case events lane, and a money lane when a ledger exists. Money sits on its day, never at a time of day.
  2. Window chips (±1 h, ±6 h, ±24 h, custom), with the zone named.
  3. Communications show by default. Device events and sensor samples are counted and one click away.
  4. "No data" is drawn apart from "Phone recording, no use seen".
- **Saves:** add the selection to a finding, or "Add these to the Timeline". Save the anchor as a case key date.
- **Targets:** "What did each phone do in the 2 hours before [time]" answered and saved in 4 min or less [M]; the window opens in 5 s or less [S]; one Lanes component serves Timeline, Day view and the incident window (a code check counts 1 component) [S].
- **Failure states:**
  - Date-only anchor: "This payment has a date but no time. Showing the whole day."
  - "5,000 of 41,000 passive items shown as a summary. Show all."
- **Testable from:** J-5a (phone lanes and the case lane, from a record or key date) in Gate F (cb-pol), using 03-2 from cb-screens through the agreed hand-off. J-5b (money lane, payment start) in the cb-crossev gate. J-5c (incident window, statement-claim start) in the cb-approaches gate.

### J-6 Search everything and read the hit in context

- **Steps:**
  1. Cmd/Ctrl+K or the header box gives grouped results with exact totals: messages, people, records, calls, emails, documents, media.
  2. Arrow keys move. Enter opens the highlighted hit, starting on the group with the highest-scoring top hit.
  3. A message hit opens the whole unfiltered thread at that message, with matches highlighted: "Showing the whole conversation. Your search matched 12 messages here. Next match."
  4. "Back to results", or browser Back, restores the query and scroll position.
  5. "Show all 1,874 in Conversations" turns the search into a filter.
- **Saves:** add a hit or the whole result to a container. Save the search as a keyword list that runs on every phone, including phones added later.
- **Targets:** query to a hit read in context and collected in 60 s or less [M]; search p95 1.5 s or less over the http address [S]; rate of searches with no results [I].
- **Failure states:**
  - "Type at least 3 letters."
  - "No message on these 14 phones contains this. 2 phones have unreadable records (why)."
  - Slashes and plus signs are handled.
- **Testable from:** 03-5, in the cb-screens gate.

### J-7 Who is who: link identities and set owners

- **Start:** **Needs a decision**, then People suggestions. Also from Dossiers, Phone identities, the Conversations notice and (once edges exist) Graph nodes.
- **Steps:**
  1. A docked, non-modal panel steps through one suggestion at a time, highest score first, with a filter by reason.
  2. Each suggestion shows the name saved on each phone with its number, the reasons, and 3 example records per reason with counts. A suggestion never rests on names alone.
  3. Keys: `y` **Link**, `x` **Not the same person**, `s` Skip, j/k move. A progress line reads "12 of 36 decided". The decision stores a standard reason built from the reasons shown (4.11), plus an optional note.
  4. **Unlink** and **Split** are offered on linked identities. Each previews its effect, needs a typed reason, and can be reversed from the dossier history (03 10.3).
  5. A batch is allowed only within one reason, after a preview. Each item gets its own decision record.
  6. Set the owner from the Phone summary.
- **Saves:** the decision log and the corrections feed.
- **Targets:** median 20 s or less per decision [I, M]; acceptance rate per reason, which 02 8.7 needs to keep or change a rule [I].
- **Failure states:**
  - "Someone else changed this person while you were reviewing. Their change is shown below. Your choice was not saved. Choose again." The selection is kept.
  - "Suggestions for this phone's own accounts appear once the owner is linked."
  - Disabled controls state the reason: "A case admin can change links."
- **Testable from:** backend suggestion and decision tests (U-backend) in the cb-interpret gate. J-7 in the cb-screens gate (03-8 People, 03-4 Phone summary).

### J-8 Check the system's readings

- **Start:** the "Needs a decision" count in the sidebar, the unconfirmed count in any totals line, or the "Mapped by the system, not yet confirmed" mark on a row.
- **Steps:**
  1. Readings are grouped by phone and type and ordered by records affected, each as a plain sentence: "On C3, chat messages: the From field is read as the sender. Affects 41,233 messages."
  2. **Examples** are drawn from the whole affected set and cover each kind present: incoming and outgoing, one-to-one and group, each app version, and edge cases (empty field, system message). They are rendered as they appear on screen, beside the choice, with "4 of 4 kinds viewed". **Looks right** stays disabled until every kind has been shown.
  3. **Looks right** (`y`) records a confirmation with the standard reason "Confirmed on the review screen after viewing 12 examples across 4 kinds" and an optional note.
  4. **Not right** (`x`) offers plain choices, for example "The sender is the other party" or "This is when it was read, not sent", plus an optional note. The correction applies to this phone in this case (4.11). Re-reading shows progress: "Re-reading 41,233 messages: 12,000 done, about 40 s left. Screens show the earlier reading until this finishes."
  5. Skip (`s`).
  6. "Looks right for all 12 rows of this kind on this phone" lists each row with its examples first.
  7. The record panel offers the same choice beside its mark, so review also happens while reading.
- **Saves:** a decision under the person's name, through the corrections feed with a phone pattern key.
- **Targets:**
  - Median of 20 s or less per reading, and the 20 readings that affect the most records in 20 min or less [M, I].
  - Participants explain correctly what "not yet confirmed" means [M].
  - Quality: a second person re-checks a 5% sample of confirmations, and the disagreement rate is reported [I]. Speed figures are reported but are never success measures on their own.
- **Failure states:**
  - "[name] confirmed this 2 minutes ago. Your view is updated." The place in the queue is kept.
  - "Your correction is saved but not applied yet. The earlier reading is still shown. Retry."
  - A correction that would empty a screen is previewed: "After this change, 2,140 messages will have no sender. Continue or cancel."
- **Testable from:** J-8a (the Needs a decision page, readings group) in the cb-interpret gate. J-8b (from the record panel) in the cb-screens gate.

### J-9 Test a statement against the phones

- **Steps:**
  1. Enter claims, each beside the statement's own words. Claims are typed, or drafted by the model and marked "Drafted by <model>, not confirmed" until each field is confirmed. Drafting uses the existing model policy with full phone visibility (7.1).
  2. A place given as text is resolved with a map or address-dossier picker.
  3. Evaluate. Each claim gets a result in the fixed wording, and gaps are listed.
  4. Items are grouped as supports, undercuts and context, with exact counts. All stay reachable.
  5. "What would contradict this?" lists searches not yet run.
  6. "This item is wrong" opens the record correction or marks the item disputed. The computed outcome is never overridden by hand. A stale result shows **Check again**.
- **Saves:** items are attached to a finding or theory with a role each. The statement check is linked to the interview on the dossier (section 6).
- **Targets:** a 3-claim statement checked and attached in 10 min or less [M]; the check takes 2 s or less and is identical on re-run with unchanged inputs [S].
- **Failure states:**
  - "This check needs C3's owner linked to this person. Link now."
  - "AI drafting could not run. Enter claims by hand, or try again." (the model call failed or timed out)
- **Testable from:** Gate F (cb-pol). Attaching to an interview needs lx-collect item E.

### J-10 Where was the phone, and were two people together

- **Steps:**
  1. Points draw their uncertainty circle. A point with no accuracy is dashed and labelled "Accuracy not recorded" (51,056 of 63,784 location records have none, *measured*).
  2. A summary line: "Showing 1,204 of 1,260 positioned records. 56 cannot be placed (why)."
  3. The time strip filters the map. Area selection lists "Phones seen in this area".
  4. **Together** returns compatible, separated or undetermined per episode, with the assumed radius shown. A broad overlap is never called together.
  5. Location wording follows cell-site practice: "consistent with" appears only with the alternatives listed.
- **Saves:** points, or a Together result frozen as a snapshot, go into a finding. A place can become an address dossier.
- **Targets:** from a message to positions within the hour in 3 actions or fewer [S]; a two-person check over one week in 5 min or less [M]; Together shows progress within 2 s and finishes in 60 s or less [S].
- **Failure states:**
  - "No positioned records within 1 hour of this message. The nearest is 3 h 12 min earlier. Show it."
  - "Cell towers cannot be placed in this case yet."
  - "Comparing 2,400,000 pairs of points: 38% done, about 40 s left."
- **Testable from:** J-10a (Map layer, positions) in the cb-screens gate. J-10b (Together on the Patterns screen) in Gate F. J-10c (Together drawn on the Map) in the gate of whichever of the two jobs finishes second; the other job tells it through `tell.sh`.

### J-11 Find deleted or concealed material

- **Steps:**
  1. State chips: deleted, in trash, recovered by carving, synced from another device, unreadable. Each can be set to include, exclude or show only.
  2. Rows read "Deleted at some time between [time] and the extraction".
  3. "Also on C2" opens both copies side by side. "Only on this phone" gives the reason.
- **Targets:** all deleted messages between a pair listed in 3 min or less [M]; 3 actions or fewer from the summary [S].
- **Failure states:** a carved fragment with no time is listed at the end and counted.
- **Testable from:** cb-screens gate.

### J-12 Build the case while reading

Section 6 has the detail.

- **Steps:**
  1. Select one item or several: Space, Shift+click, Shift+J/K, or Ctrl/Cmd+A for the whole filtered total ("All 186,787 messages selected").
  2. `c` opens **Add to…**, then `d` dossier, `w` finding or theory, `n` note, `t` Timeline, `l` label.
  3. Recent targets come first, and a linked person's dossier is offered first.
  4. For a finding, pick Supports, Contradicts, Context or Unclassified. For a dossier, pick a role: link, contact, photo, assessment support or interview evidence.
  5. The reply: "Added 412 messages to [finding]. 3 were already there. Undo." Undo is also kept in the target's history.
  6. Rows now show "In 1 finding, 1 dossier".
  - A key-triggered action on more than 5,000 records asks for confirmation first.
- **Targets:**
  - One item in 3 actions or fewer and 5 s or less of human time [M].
  - 5,000 items in 10 s or less with a progress panel [S].
  - A photo, two contacts and three messages added to a dossier in 4 min or less, each found again from the dossier [M].
- **Failure states:**
  - "This finding changed since you opened it. Your 412 messages are still selected. Add them again."
  - Container limits are stated and handled in parts: "Timeline takes 5,000 at a time; 12,345 selected. Add in 3 parts." Nothing is clipped.
  - "Already in this dossier (added by [name] on [date])."
- **Testable from:** cb-screens gate, on surfaces that exist by then (CO matrix, section 6).

### J-13 Share the review and know what is left

- **Steps:**
  1. From a saved view, "Split for review" creates existing Workspace tasks, by thread or person, each assigned to a person.
  2. Reviewers mark threads reviewed (`m`). The mark is a task link to the thread (section 6) that records who, when, the scope and the record count at that moment.
  3. Every screen shows "Not yet reviewed: 3,210 of 4,491 threads".
  4. When a thread's record count changes after review (Replace, re-reading, widened scope), the header says "Reviewed by [name] on [date] (1,204 messages); 38 added since". The coverage summary counts it as partly reviewed.
  5. An optional second pass samples 10% of reviewed threads for a second person.
  6. The coverage summary lists searches run, terms used, who reviewed what, and what was not reviewed. It feeds the export cover.
- **Targets:** a lead says what remains unreviewed in 30 s or less [M]; the coverage summary always equals the marks [S].
- **Failure states:** "[name] is also reviewing this thread."
- **Tests:** J-13, and J-13b: after a Replace that adds messages, the coverage summary drops the thread from "reviewed" to "partly reviewed".
- **Testable from:** cb-screens gate.

### J-14 Export for counsel

- **Steps:**
  1. The dialog states the scope in words: "All 2,140 messages and 48 calls between A and B, 1 Jan to 31 Mar, on 3 phones, times in Eastern time. Saved passwords and card numbers left out."
  2. The cover states the reading state: "412 of these 2,188 rows rely on readings not yet confirmed by a person; 6 transcripts are machine-generated and unconfirmed. Review them first." The last sentence links to Needs a decision.
  3. Choices: the conversation, or an all-channel timeline; plus an appendix of what was examined.
  4. A first-page preview, drawn by the same formatter.
  5. Progress in the job tray: "Drawing page 140 of about 310, about 40 s left". A notice when done, and history kept on the dialog and the Phone summary.
- **Rows:** each exported row carries its origin mark (4.6). A corrected row prints the original beside the corrected value. Copied text does the same.
- **Targets:** 2 min or less of active time and 8 actions or fewer [M]; the cover total equals the screen total [S].
- **Failure states:**
  - A character missing from the fonts is drawn as [U+...] and counted on the cover.
  - A failed render keeps the choices and offers Try again with a reference id. Nothing is half-delivered.
- **Testable from:** J-14a (conversation, timeline, Phone summary, finding, dossier and collection sources) in the cb-screens gate. J-14b (statement check, analysis result and incident window sources) in the cb-approaches gate.

### J-15 Resume and hand over

- **Steps:**
  1. **Continue reading** on the Phone summary and in the case "Your work" feed lists threads opened and not finished, each with its last position.
  2. For an assigned review, the position is stored on the review task link, so it survives the browser and passes to a colleague. For unassigned reading it is kept in the viewer's browser storage, as record ids only.
  3. **Since you last looked** gives counts per change kind: new phone, Replace, re-readings, colleagues' confirmations and links.
  4. **Hand over** on a review task reassigns it and attaches a handover note (a Workspace note linked to the task) that lists positions and open items.
- **Targets:** resuming takes 2 actions or fewer [S]; a colleague finds the open items in 60 s or less [M].
- **Testable from:** cb-screens gate.

### J-16 Compare phones for a person or a pair

- **Start:** a dossier's "On the phones" panel, or the scope bar when exactly 2 phones are selected.
- **Steps:**
  1. Two columns, one per phone, aligned by matched message.
  2. Counts: "on both", "only on C5 (reason)", "only on C6".
  3. Each phone's saved name and number for the person, coverage bands, and differences in deleted state.
  4. **Add to…** works on the differences.
- **Targets:** what each phone holds about a person, compared in 3 min or less [M]. The per-pair counts equal the record query [S], and equal approach 12's result once that exists (cb-approaches).
- **Testable from:** cb-screens gate. The approach-12 equality is in the cb-approaches gate.

### J-17 Explain a finding

- **What it is:** every finding that holds phone links shows a generated block, **How this was found**. Nothing in it is typed. It holds:
  - the saved scope and the searches behind it
  - the identity decisions and readings the finding relies on, with their confirmation state
  - assumptions taken from the undercut codes (owner, clock, completeness)
  - the label "Lead for enquiry" or "Result for report"
- **Export:** the block is the first page of a finding export.
- **Targets:** brief counsel on one finding in 5 min or less [M]. The block's counts equal the links and decisions behind it [S].
- **Testable from:** cb-screens gate. Statement-check and analysis inputs are added in the cb-approaches gate.

---

## 4. Rules for every phone screen and phone layer (UX-)

03 3.12 points here. These rules apply to every phone screen and to every phone layer on a shared screen.

### 4.1 Reuse what Loupe has

| Need | Reuse | Change |
|---|---|---|
| Waiting standard | `features/financial/components/LoadProgress.tsx`, `lib/request-progress.ts` | Copy into `components/ui` and `lib` as shared components. Count requests flagged as reads (phone reads are POST). The financial originals stay until their owner moves them. |
| Previous-copy notice | `FinancialViewUpdatingNotice.tsx` | Generic version for stale snapshots and re-reading |
| Confirm or correct | `JudgementCalls.tsx` ("Looks right" / "Correct it") | Examples by kind; standard reasons (4.11) |
| Model-reading mark | `PaymentLabelOrigin.tsx` | Generalised to the origin mark (4.6), using theme tokens |
| Absence sentences, citations | `SourceHighlight.tsx`, `source-citation.ts` | The record panel follows this pattern |
| Guided queue | `queue-guidance.ts` | Needs a decision |
| Docked keyboard review | `PaymentNamingPanel.tsx` (non-modal aside) | Record panel, suggestion panel. Not the modal `Sheet`, which stops j/k. |
| Guide and checklist | `FinancialGuide.tsx` | A generic Guide dialog |
| Drafts | `financial-drafts.ts` | Claim and note drafts |
| Insecure-context helpers | `lib/browser-crypto.ts` randomRequestId; `StatementSourceTools.tsx` copy fallback | One shared copy helper |
| Reverse lookup | `NotebookLinkedNotes.tsx` | "In 2 findings, 1 dossier" |
| Add-to dialogs | `AddEvidenceToDossierDialog.tsx`, `AddToTimelineDialog.tsx` | One **Add to…** menu |
| Attention feed | `CanonicalWorkspaceOverview.tsx` ("Your work") | Phone ready or failed, export ready, decisions waiting, Continue reading |
| Speed measurement | `lib/route-speed.ts` | Phone sub-routes recorded instead of "other" |
| Layout check | Timeline layout overlap-count scripts | Journey-test layout assertion |
| Usability browser tests | `EvidenceUsability.browser.test.tsx` | Model for phone tests |

### 4.2 Loupe-wide inconsistencies phones meet, and who fixes each

Each fix has a test that fails on today's code. The owner is the unit 06 section 6 names where it names one. cb-ux builds only new shared components.

| # | Inconsistency | Owner |
|---|---|---|
| 1 | Bare spinners in 60 non-test files, including the route fallback and the Timeline, Map, Graph, Table and Dossiers pages | Each phone unit replaces the spinner on every screen it adds phone data to. The route fallback gets words in 03-1. The rest goes to `followups`. |
| 2 | The API client counts every successful POST as this tab's own write, which turns off Financial's "updating" answers for 120 s | `followups`, with test XF-9. Phone screens send read-flagged requests. |
| 3 | Amber is aliased to the brand carmine (619 uses in 139 files) | Phone screens use new semantic tokens: `status-review`, `status-model`, `status-deleted`, `status-error`, at 4.5:1 in light and dark (cb-ux). The app-wide alias goes to `followups` with a screenshot comparison. |
| 4 | 612 uses of 9 to 11 px text; badge contrast about 2.7:1 to 4.35:1 (**estimate, not measured**) | Phone screens use 12 px or more for data, and 11 px only for metadata at 4.5:1, with contrast measured in the browser |
| 5 | Cmd/Ctrl+K fires an event nothing listens to | 03-5 (06 section 6) |
| 6 | Three list models: Timeline loads everything, Evidence pages 250, Financial pages 50 | Phone screens use exact-total virtual lists only |
| 7 | Selection on Map, Table and Timeline means a graph node, and phone records are not nodes | Phone selection store (cb-ux), read by the side panel and the Notebook |
| 8 | Case pages have no heading and the tab title never changes | Phone screens use `PageHeader` and set `document.title` |
| 9 | The vendor name appears in the sidebar, job card, upload tooltip and Settings | "Phone report" and "Phones", in 01 and 03 units |
| 10 | `window.prompt`, `window.confirm`, toast-only errors | Phone screens use in-page dialogs and inline `role=alert` messages with a reference id |
| 11 | 33 files format dates their own way | One formatter (`lib/evidence-time.ts`) for screen, copy and PDF across the Timeline, in 03-6 and 03 15.6 |
| 12 | Two permission hooks disagree about super admin | `followups` |
| 13 | The theme loader calls localStorage without try/catch | `followups`. Phone code wraps all storage. |
| 14 | "Phone" means a narrow screen in Timeline code | `followups` |

### 4.3 Layout

- One purpose per screen, and at most two work areas side by side.
- The record panel is the Details content of the existing case side panel. It is non-modal: j/k keep moving and it follows the focused row.
- When Chat or the Notebook opens from a record, the composer shows a compact pinned preview of the record or records with "Open the record", so writing about a message never hides it.
- Below 1440 px the Conversations thread list collapses to a 48 px rail ("Threads (4,491)"). The breakpoint is a decision, reversed if R1 shows the list is needed open.
- The first work item is visible without scrolling at 1280×720. Status cards are one 48 px line.
- Targets: 1280×720, 1440×900 and 1920×1080. At 390 px, screens are readable for reading only.

### 4.4 Density and row anatomy

- Two densities, Comfortable (default) and Compact. Neither removes the name or the number.
- Mixed streams show "Name (number) → Name (number)" on every row. One-to-one threads carry both sides in the header, and each row shows the arrow (with an aria-label) and the sender. Copy and export always use the full form.
- Alex's combined label "[case label] · [phone's name] (number)" is the default. The compact form is a person's setting.
- **Row line 1:** time (12-hour; seconds when two rows share a minute), direction, participants, app, at most two badges plus "+N". Then the full text. Replies and quotes show as an indented block linked to the original.
- **Lists to compare** use one shared virtual table: calls, contacts, locations, accounts, apps, approach results, and the list for each record type. It has sortable columns, keyboard-resizable columns, an exact total and one selection model.

### 4.5 One scope, carried everywhere

- A **scope bar** on every phone screen and layer holds people, phones, window, labels and kinds as removable chips, with the resulting count.
- **Presets:** "Phones of <dossier>" (owner-linked), "Phones where <person> appears", and the last 5 scopes. Test: from a dossier to a scope of that person's phones in 2 actions.
- The scope lives in the URL and is remembered per case for the session ("Showing your last selection: 3 phones. Reset").
- Crossings carry the scope, and the receiving screen shows the same chips and the same count, from one backend query module per result kind (03 D-4):
  - "Show on Timeline"
  - "Show on Map"
  - "Open in Graph"
  - "Open these payments"
  - "Ask the agent about this"
- Phone chips show the label, plus the extraction date when labels collide ("C1 · 3 May").
- **Return path.** Browser Back and reload restore filters, selection, open panel and scroll, anchored on the record id. This holds across the reload notice after a release. After a jump, a "Back to Conversations (A → B, March)" chip appears.

### 4.6 Where each value came from: one origin mark

The marks are part of the shared formatter, so screen, copy and PDF print the same mark.

| State | Wording | Treatment |
|---|---|---|
| From the report | no mark | plain |
| Read by the system, not confirmed | "Mapped by the system, not yet confirmed", with the rule in plain words on click | review token + icon |
| Machine-generated | "Machine-generated by <model> <version> on <date>, not yet confirmed" | model token + icon; the source stays above |
| Confirmed | "Confirmed by <name> on <date>" | plain, in the record panel |
| Accepted model reading | "Read by <model>, accepted by <name> on <date>" | model token |
| Corrected | "Corrected by <name> on <date>: <reason>", with the original shown beside it | correction token + icon; only the corrected value is searched, summed or exported as the value |

- **Badge priority:** corrected, not confirmed, deleted or recovered, from another device, duplicate, then others. Two show, and "+N" lists the rest.
- Every badge has a meaning sentence from one glossary file shared with the guide.
- Totals lines state "N not yet confirmed" whenever the result holds unconfirmed readings.

### 4.7 The waiting standard

- The shared panel shows after 300 ms, and data or words appear within 2 s.
- It names the step ("Counting matching messages on 3 phones") and gives completion from true counts ("98,000 of 186,787").
- **Time left** ("about 40 s left") comes from the measured rate of this step or this view's last load. With no rate history it says "Working out time left (first run of this step)", never an invented figure.
- It updates at least every 1 s and never shows 100% before the page is drawn.
- **Stall rule, one for every surface:**
  - Interactive reads say "Still working on <step>" after 3 s with no movement, and name the slow part with Try again after 10 s.
  - Background stages (intake, interpretation, derivation, export) say "No change on <step> for <n> s. The server is still on this step. Last change at [time]" after a per-step-kind threshold. Each threshold is set from measured step rates, and starts at 30 s for intake stages (a decision, reversed once rates are measured).
- **Job tray.** Long work reports every 1 s through a header job tray, which lists each job in words with time left and gives a notice and link when done. This covers intake, interpretation, re-reading, export, transcription, text read from images, thumbnails, Together, Routine, approach runs, bulk collect and agent phone tool calls. Server progress is published every 1 s while work runs.
- No bare spinner appears on any phone screen or layer.

### 4.8 No silent truncation, one wording

- One count component: "Showing 1,204 of 1,260 [things]", with thousands separators, the reason, and how to see the rest. "N / M" is never used.
- No "Load more" anywhere. A limit is stated with its number, and raising it is never the fix.
- **Find in these results:** a visible Find control and the first Ctrl/Cmd+F search the whole result on the server ("Match 3 of 214"). A second press passes to the browser. Browser find is not relied on over virtual lists, which keep most rows out of the page.
- Graph and Timeline say what they aggregate. Agent results state their scope. Bulk actions report added, already-present and refused counts.
- The casework "current selection" stops keeping only the first 6 items, for phone, graph and evidence selections alike (lx-collect).

### 4.9 Keyboard

There is one keymap registry, and every key has a visible control. `?` shows the keys for the current screen, generated from the registry. Focus is tracked by record id. One key has one meaning across all queues, and the visible label names the outcome.

| Key | Action |
|---|---|
| j / k, arrows | move |
| Shift+J / Shift+K, Shift+Arrow | extend selection (03 3.9) |
| Enter | open |
| r | record panel |
| a | around this time |
| c, then d / w / n / t / l | add to dossier / finding or theory / note / Timeline / label |
| / | focus the filter search box (03 3.9) |
| Ctrl/Cmd+F | find in these results (second press: browser) |
| g | go to date (also a button) |
| Alt+J / Alt+K | next / previous day (also buttons in the day header) |
| o | original time value (03 3.9) |
| p | names: this phone / case (03 3.9) |
| m | mark reviewed |
| y / x / s | Yes (Looks right, Link) / No (Not right, Not the same person) / Skip, in every queue. The financial naming panel's arrow keys stay as aliases. |
| Esc | close or return |

- Alt+J/K, Ctrl/Cmd+F and Ctrl/Cmd+6 are kept only where a browser test on the http address shows the page receives them in Chrome and Firefox. The visible controls and the palette are the reliable path.
- A key-triggered action on more than 5,000 records asks for confirmation.

### 4.10 Plain http (an insecure context)

- **Copy.** Up to 5,000 rows in memory: copy runs inside the click through the copy event, writing plain text and HTML. Larger copies take two steps: "12,345 messages are ready to copy. Copy now." If the browser refuses, the text is selected with "Press Ctrl+C".
- One shared copy helper also serves Graph "Copy Key" and Chat.
- Ids come from `randomRequestId`. No service workers.
- Every browser test asserts `window.isSecureContext === false`.

### 4.11 Decisions, reasons, errors, permissions, welfare, words

- **Decisions** use in-page dialogs that state the consequence: "Link these 3 numbers to A. 1,204 messages will show under A. Undo from A's history."
- **Reasons.** Every decision is recorded through `decisions.record`, which refuses a blank reason.
  - Routine confirmations and identity links record a **standard reason** built from what was shown, for example "Confirmed on the review screen after viewing 12 examples across 4 kinds". It is stored with `reason_kind = standard` and displayed as "Standard reason", never as the person's words. An optional note is added.
  - A typed reason is required for value corrections, Unlink, Split, replacing or retiring a report, accepting a reconciliation difference, and the external-processing decision.
- **Scope of a reading decision.** A confirmation or correction made on a case screen applies to that phone in that case. It is stored as a case-scoped decision on (case, extraction, mapping row, mapping version), and a correction re-derives only that extraction. Optionally it applies to the other phones in the case with the same report format, listed by label first. The global mapping registry is changed only by an admin from the admin list, where case corrections appear as proposals (02 6.8).
- **Errors** stay on the page (`role=alert`) with a reference id and Try again. Toasts are only for success with Undo. Error copy reads "Reference: <id>".
- **Permissions.** Controls a person may not use are disabled with the reason. A refusal after a click never happens.
- **Welfare.** In criminal cases, thumbnails are blurred until opened. They can be revealed one at a time or per phone, and each person can turn this off. This is an inference with no source (section 16).
- **Words.**
  - No em dashes, no internal names, and no activity implied from no data.
  - Zones are named in words with the offset ("Eastern time (UTC-4)").
  - The extraction profile is called **Phone summary**.
- **Accessibility.** WCAG 2.2 AA. Lists expose position and size. Reduced motion is respected. The phone palette has 10 colour-blind-safe hues, always paired with the label, and with a marker shape on the map.

### 4.12 Defaults that do not move under people

The Timeline lens and Map layer start **on** when the case has no other dated events or located items, and off otherwise ("48,912 phone entries hidden. Show"). The state is stored per person and case at first use, and is not recomputed from case contents. When case contents change, the state stays, and the screen says "Phone entries are shown. This case now also has documents."

### 4.13 Routes

- Phone pages:
  - `/cases/:id/phones`
  - `/cases/:id/phones/:extractionId`
  - `/cases/:id/phones/:extractionId/records/:type`
- Case-wide phone pages use distinct segments, so they cannot be matched as extraction ids:
  - `/cases/:id/phone-review`
  - `/cases/:id/phone-patterns`
  - `/cases/:id/phone-analyses/:approach`
- A router test asserts each route.
- A sidebar group **Phones** is shown when the case has a phone: Phone summary list, Conversations, Media, Patterns, and **Needs a decision** with its open count.
- The palette covers every phone screen.
- UX-1: every route is reachable from visible controls.

---

## 5. Screen-by-screen

The owning spec holds each item. Section 15 gives the edit and the test ids. New 03 decisions start at D-27. New test ids are checked against the owning spec before use, and a taken id moves to the next free number.

- **Shared phone components** (`features/phones/ui`, plus `components/ui` where Loupe-wide), built by cb-ux. Each has Storybook stories in light and dark, with accessibility checks that fail the build:
  - scope bar, phone table, record panel content
  - Add to… menu, origin mark, result count
  - progress panel and job tray, time strip, phone chip
  - keymap overlay, guide dialog, copy helper
- **Phones list and Phone summary (03 7).**
  - The verdict line and triage block (J-2).
  - A Needs a decision box with working controls: owner, device zone and applying it to times with no offset, default region (the response gains "N numbers were read assuming <region>"), clock offset, phone label, identity label, accepting a reconciliation difference, Replace or Retire, and a link for external processing.
  - Where to start, Continue reading, Since you last looked, and export history.
  - Tests: P-6 (each control writes a decision and a feed line, and appears in history), P-7 (the verdict matches reconciliation), J-2.
- **List for each record type** (new 03 section). The shared table with columns from the type's mapping. It is reached from every count on the summary. Test P-8: every type with records has a list whose total equals the summary count.
- **Conversations (03 6).**
  - Opening state: "Pick a thread or a person. The busiest are listed first."
  - Thread list: quick-find, sorts, phone group headers.
  - Participant modes: Sent by, Sent to, Between, Involving.
  - The time strip.
  - Replies, quotes and forwards shown.
  - All channels, Around this time, multi-select Add to…, Mark reviewed.
  - **Attachments (N)** in the thread header. It opens the Media grid filtered to the thread scope, with the scope chips, next and previous with the parent message shown, and Back to the stream position. The thread header and export cover state "14 attachments referenced, 3 not in the report".
  - Tests:
    - C-10: "Sent by X to Y" for a pair that excludes the owner equals the record query.
    - C-11: a hit opens in the full thread.
    - C-12: Around this time opens in place and leaves the anchor unchanged.
    - C-13: a person's "Not a copy" decision on a duplicate.
    - MD-1: attachment counts equal Media under the same scope, and Back restores the anchor.
    - A15, redefined to the time strip and stream filling their space at 1280×800 and 1920×1080.
    - A16, with a reference id.
    - UX-2: find covers rows outside the viewport.
    - UX-3: copy on http.
    - UX-4: the panel is non-modal and j/k move.
- **Record panel (03 3.6).**
  - Actions: Add to…; Correct this value (02 10.4: typed reason, original kept and shown); the reading choice; Around this time; Open the window around this.
  - Blocks: "Used in this case" (resolving selections, section 6) and the link state.
  - Tests: UX-5 (a corrected value shows both values, and only the corrected value is searched, summed and exported), CO-7.
- **Needs a decision** (02 6.8; cb-interpret builds the page and its readings group, cb-screens adds the other groups).
  - Groups: readings to check, people suggestions, phone setup, machine text in use. Each has a progress line ("7 of 21 checked").
  - The interpretation level gains `applied_unconfirmed`.
  - Correction choices come from a closed list per mapping kind, so nobody edits JSON.
  - Registry flags and proposed global corrections appear in an admin-only list.
  - Tests:
    - RQ-1: no field names in body copy
    - RQ-2: examples cover each kind, and Looks right is disabled until they are viewed
    - RQ-3: a standard reason is stored and labelled
    - RQ-4: a correction re-derives only its scope, with progress
    - RQ-5: one feed line per action
    - RQ-6: conflict wording
    - RQ-7: a case correction leaves other cases' derived values unchanged
    - RQ-8: whether examples were opened is recorded with each decision
- **Media (03 8; derivation by cb-media).**
  - Viewer next and previous, keys, size, blur.
  - Linked messages open keeping the reader's place.
  - Batch derivation in the job tray ("Transcribe all 312 voice notes in this scope"). CPU speed is measured before targets are set.
  - **Machine text is confirmed on use.** Adding machine text to a container, quoting it in a finding or exporting it prompts "This transcript is machine-generated. Listen and confirm, or keep it marked", with the audio inline. Everything else stays marked. Needs a decision lists only machine text already in use.
  - Tests: M-5 (batch progress updates every 1 s from true counts), M-6 (a corrected transcript is searched and its original stays), M-7 (exporting an added, unconfirmed transcript shows the prompt and prints the mark).
- **Timeline lens (03 9).**
  - Default kinds: messages, calls, emails, media, location stays. Device events and sensor samples are off and counted per case ("[N] device events and sensor readings hidden. Show"). Repeated device events are grouped.
  - Defaults follow 4.12.
  - One formatter for the whole Timeline, and one Lanes component.
  - Add to Timeline works for phone records.
  - Tests: T-7 (default kinds and the hidden count). T-5 is extended to assert that the lens off restores the existing page exactly.
- **People (03 10).** The suggestion panel (J-7), with Unlink and Split. "Add to Dossiers" on a PhoneIdentity graph node routes into the link decision. Tests: U-5 (order and keys), U-6 (a batch within a reason writes one decision per item), U-7 (a read-only person sees disabled controls with the reason), U-8 (Unlink and Split preview, need a typed reason and are reversible).
- **Search (03 11).**
  - The Enter rule, hits in context, Back restores, calls and emails groups, saved keyword lists, symbol handling.
  - Recent queries are kept in sessionStorage only, wrapped in try/catch, and are gone when the tab closes.
  - Tests: S-8 (a hit opens in the full thread), S-9 (Back restores results and position), S-10 (slashes and plus signs).
- **Map (03 13).** Palette with labels and shapes, keyboard stepping through clusters, empty "Show on Map" wording, area selection, defaults per 4.12. Tests: G-5 (palette contrast and labels), G-6 (empty-result wording).
- **Graph (03 14; edges from 02-U16 in stage G).** One aggregated edge per pair with counts, and sums where a ledger is linked. "Conversations on the phones (1,204 messages, 38 calls on 3 phones). Open" in the node panel. First draw within 3 s at 2,000 nodes (target, to be measured). Tests: R-4 (phone-edge graph search), R-5, XF-2.
- **Export (03 12).** The dialog with preview, job tray progress, notice and history; origin marks per row with counts on the cover; new sources `collection`, `finding`, `dossier`, `statement_check`, `analysis_result` and `incident_window`; the appendix of what was examined; the "How this was found" page. Tests:
  - E-8: the preview equals page 1.
  - E-9: a collection total equals the collected count.
  - E-10: an export of a scope with unconfirmed readings prints the mark per row and the count on the cover, and copied text does the same.
- **Intake (01; Evidence job card).**
  - The upload panel with hashing and sending progress and time left. One readiness card through to ready, and `pv_extraction.state` gains `interpreting` and `building_views`.
  - Plain stage words replace "Chunking" and "Extracting Entities", and em dashes are removed from the uploads panel.
  - Notices go to the attention feed. Cancel is on the card. Replace and Retire work. A protected file creates a task. The owner prompt comes after capture.
  - Tests: I-1 (a panel within 2 s, updates every 1 s, true counts), I-2 (Replace retires the older report and every count changes once).
- **Patterns and analyses (04, 05).**
  - Patterns holds Day view, Pattern grid, Places over time, Together and Statement check, with a subject picker.
  - Analyses share one layout: what it does, Run with progress, the coverage sentence, results with total, the record panel, Add to…, and confirm or reject with a typed reason. Results are labelled "Lead for enquiry".
  - **Key dates and case terms** are Workspace entries with a key-date marker that hold an instant and zone. They are entered once per case and reused by every analysis.
  - Tests: POL-1 (reachable from the sidebar), AP-1 (common layout and coverage sentence).
- **Case settings.** A Phones section holds zone, default region, external processing (with its plain consequence), blur default and tower reference (admin). The "Times are shown in UTC" sentence links here.

---

## 6. Building the case: phone material into Loupe's existing system

Every phone item can be collected as the investigator works: message, call, email, contact, location point or stay, media file, conversation, identity, phone, pattern-of-life finding, statement check and analysis result. It goes into Loupe's existing dossiers, Workspace notes, findings and theories, tasks, Timeline curation and Significant, and keeps a link back to the record with its provenance. The phone piece builds no collection system of its own. The unused Loupes tables are not built on.

**The existing system, as used:**
- **Dossiers** (`case_profiles`): links, contacts, media, assessments with model provenance, interviews. Subject types are person, address, event, device, organisation, vehicle and other.
- **Workspace** notes, findings and theories, with links, revisions, events and tags. The Notebook is a view over them.
- **Tasks** (`case_tasks`, with `case_task_links` carrying a target type, target id and source anchor), **Timeline** curation and saved views, **Significant** (graph keys only), and **Workspace AI** (cited, accepted by a person).

### 6.1 What goes where

| Phone item (link type) | Dossier | Finding or theory | Note | Timeline | Task | Significant |
|---|---|---|---|---|---|---|
| Message, call, email, calendar, note, any record (`phone_record`) | Link, assessment support, interview evidence | Link with relationship | Yes | Yes, with instant and zone | Yes | No |
| Contact record | Dossier contact citing its source record | Yes | Yes | No | Yes | No |
| Location point or stay | Link; address dossier | Yes | Yes | Yes | Yes | No |
| Media file, voice note, call recording (`phone_file`) | Gallery, cover or interview evidence (that one file registered, 6.4) | Yes | Yes | Yes | Yes | No |
| Conversation, whole or a window (`phone_thread`) | Link | Yes | Yes | No | Review mark | No |
| Identity (`phone_identity`) | Only through the link decision | Yes | Yes | No | Yes | Yes |
| Phone (`phone_extraction`) | Device dossier | Yes | Yes | No | Yes | Yes |
| Pattern or analysis result (`phone_analysis` snapshot), statement check (`statement_check`) | Assessment support; interview evidence | Yes, frozen, stale on recompute | Yes | Yes (period) | Yes | No |
| Selection over 500 records (`phone_selection`) | One link with a frozen record list and the scope | One link | One link | Up to 5,000 per request, stated | One link | No |
| Saved view (`phone_view`) | No | No | A Workspace note holding the scope, re-run live, stating the count then and now | No | Review split source | No |
| Label (a Workspace note tagged `label`) | No | No | The label itself; records are linked to it | No | No | No |

- **Labels.** A label is a Workspace note tagged `label` ("Disclosable", "Follow up"). Applying a label links the selected records to that note. A label filters every phone screen through the scope bar, and feeds the export and the coverage appendix. Bulk apply and remove report counts, offer Undo, and write events.
- **Review marks.** A review mark is a `case_task_links` row with target type `phone_thread`. Its source anchor holds who, when, the scope, the record count at review time, and the reading position.

### 6.2 Surfaces and gestures

- **Add to…** (`c`) appears on every row, point, hit, edge, thread, file and result: Conversations, record panel, Timeline lens, Lanes, Map, Graph, Search, People, Phone summary, Media, Patterns, analyses. It works on one item or on a selection, including the whole filtered total.
- The Notebook and the note composer prefill from the phone selection ("412 selected; all 412 will be linked") and pin a preview of the records (4.3).
- Items already collected show a row badge and the record panel's "Used in this case" block. A record collected only as part of a `phone_selection` shows the badge too.
- Bulk adds use the progress panel ("Linking 4,000 of 12,345, about 6 s left") and report added, already-present and refused counts. A container's limit is stated and handled in parts.

### 6.3 Provenance on every link

- Each link stores:
  - the record address: the 02 9.9 anchor of record id, extraction, field path and character range; or the thread key, file id, identity key or snapshot id
  - the **mapping version set** behind that record at collect time
  - who added it, when, from which screen, and the relationship or role
- An optional "what this shows" note and the investigator's grade are kept apart from the automatic origin mark.
- **Link state** is worked out when the link is shown, and the stored link is never rewritten. The states:
  - active
  - **from a replaced copy of this report** (the matching record in the current copy is offered once 05-S15 record correspondence exists; until then the state is shown with no offer)
  - **corrected since collected** (both values shown)
  - **reading changed since collected** ("sender was A, now B, by [name] on [date]"; Keep or Remove is offered to the person who added it, and they are notified through the attention feed)
  - set aside as a duplicate
- Model readings stay marked wherever the item appears. When a person accepts an agent answer or machine text into a dossier assessment, it is stored with `provenance_type = ai_assisted` and `generated_output_id` (or the agent artifact id), and shows "Read by <model>, accepted by <name>".

### 6.4 Changes to the existing system (lx-collect unless named)

1. **One link-type registry**, imported by models, routers, services and a generated TypeScript type. It replaces the 11 hard-coded lists: the workspace model and its database check, the workspace router, the dossier service and its validator, the notebook service and router, the task-link check, and the frontend workspace, notebook and attachment-picker lists. Phone types are validated against the case through a resolver that cb-capture and cb-interpret register. Until they register, phone types are refused with a stated message.
2. **Dossier links:** `POST /api/dossiers/{id}/links:add` (append, idempotent, returns added and skipped counts) and `DELETE .../links/{link_id}`, both with event rows. Replacing all links no longer rewrites who added each one.
3. **Workspace links:** `POST .../entries/{id}/links:batch` with the caller's rationale ("Added from Conversations") and counts. The AI-acceptance function, which stamps "Accepted Workspace AI proposal", is never used for links people add.
4. **Phone files as evidence rows, only on demand.** A phone file becomes an evidence row only when it is added as dossier media or interview evidence. This happens one file at a time, idempotent per file id, and never in bulk. The row has `source_type = phone_file`. It is excluded from processing jobs and embedding unless the case's external-processing decision allows it (the agent and AI source collection read it in full, 7.1), and shows in Evidence as "Phone file used in a dossier", linked to its record.
5. **Interview evidence takes registry targets.** `dossier_interview_evidence_links` gains `target_type`, `target_id` and `source_anchor`. `evidence_file_id` becomes nullable, with a check that exactly one of the two is set. Existing rows are unchanged, and the row count is measured before and after the migration.
6. **Contacts** carry a record source. Contacts copied from phones are excluded from the contact-match suggestion.
7. **Reverse lookup:** `GET /api/workspace/{case}/collections?target_type&target_ids[]`, in bounded batches. It resolves `phone_selection` membership through a per-record membership index written when the link is added.
8. **Add to Timeline** gains source kind `phone_record`, with the existing preview (ready, already added, undated). Saved-view events gain `sort_instant` and `sort_zone` columns, backfilled from `sort_date` and `sort_time`. The old columns stay. Every existing saved view renders exactly as before, and the row count is measured before and after.
9. **The financial report parser** accepts the new types. Today it throws on a finding that holds a phone link.
10. **The current selection** gains a phone source and stops cutting to 6 items.
11. **Workspace and dossier views** open phone links, with label, app, time with zone and badges. Phone links join the Supports and Contradicts grouping.
12. **Graph:** "Add to Dossiers" on a PhoneIdentity routes to `link_phone_identity`. Significant is offered only on phone nodes.
13. **`phone_analysis` snapshots** freeze kind, subject, window, parameters, mapping versions, the record ids behind the result and summary counts.
14. **Exports** gain sources `collection`, `finding` and `dossier`, with the stated total equal to the collected count (with cb-screens).
15. **Agent and Workspace AI** read collections through `get_casework` and `get_dossier`, and theory analysis reads phone links. Both are built by cb-crossev with full phone visibility (7.1), not by lx-collect.

### 6.5 Acceptance tests (CO-)

| Id | Test | Gate |
|---|---|---|
| CO-1 | Matrix of surface × single or bulk × container. Each cell opens back to its record. Cells with a limit assert the parted add and the added, already-present and refused counts. | Cells for each surface in the gate of the job that builds it: cb-screens (Conversations, record panel, lens, Map, Search, People, Phone summary, Media), cb-pol (Patterns, Lanes), cb-crossev (Graph edges), cb-approaches (analyses) |
| CO-2 | A bulk add of 12,345 shows progress and ends "Added 12,342; 3 were already there". Nothing is clipped. | lx-collect (API), cb-screens (UI) |
| CO-3 | The adder and time survive another person editing the dossier | lx-collect |
| CO-4 | A phone photo as dossier cover registers exactly one evidence row with `source_type = phone_file`. No processing job is queued, no outbound request is made, and the Evidence count changes by one, labelled. | lx-collect + cb-screens |
| CO-5 | The financial report builds and reopens with a phone link | lx-collect |
| CO-6 | The Notebook prefill carries a 412-item phone selection with the pinned preview | cb-screens |
| CO-7 | "Used in this case" equals the reverse lookup | cb-screens |
| CO-8 | A corrected record shows both values on the finding and in the export | cb-screens |
| CO-9a | After Replace, a link shows "from a replaced copy" | cb-screens |
| CO-9b | ...and offers the matching record | cb-approaches |
| CO-10 | Theory analysis cites phone-linked messages, with full phone visibility | cb-crossev |
| CO-11 | `get_casework` and `get_dossier` return phone links with citations | cb-crossev |
| CO-12 | The collection export total equals the collected count | cb-screens |
| CO-13 | "Add to Dossiers" on a phone identity goes through the identity decision | cb-crossev |
| CO-14 | Every collect action and decision writes an event or feed line, on plain http, in the verification case and the phones-only case | each gate |
| CO-15 | Correcting a sender mapping flags every link to the affected records as "reading changed" and changes no stored link | cb-screens |
| CO-16 | A record collected only inside a 12,345-item selection shows "In 1 finding" | lx-collect (API), cb-screens (UI) |
| CO-17 | A message and a call attached to an interview open back to their records and appear in the interview's evidence list | lx-collect + cb-screens |
| CO-18 | Accepting an agent answer or machine transcript into a dossier assessment stores `ai_assisted` with the output id and shows "Read by <model>, accepted by <name>" | cb-crossev (agent), cb-media (transcript) |
| CO-19 | A label applied to 2,000 records filters Conversations to 2,000 and appears in the export appendix | cb-screens |
| CO-20 | A review mark appears in the task, in the coverage summary and in the export appendix | cb-screens |
| CO-21 | Existing saved Timeline views render exactly as before after the instant columns are added. The row count is unchanged. | lx-collect |

---

## 7. Working with the rest of Loupe

### 7.1 What phones provide and consume

| Loupe part | Phones provide | Phones consume |
|---|---|---|
| Agent | Read-only phone tools (schema `loupe.agent.phone_*/1`) to the ledger-tool standard: total matching, has more, limitation sentence, coverage sentence, unconfirmed readings named, a `rec://` link per record. The tools: messages and calls between people in a window, contact summary, first and last contact, activity around an instant or date, coverage gaps and deletions, places in a window, co-location results, statement-check results, record search. | Case scope, Significant |
| Timeline | Lens, Lanes, curated phone records | Case events and dated money for the case lane; the shared formatter |
| Graph | PhoneExtraction, PhoneIdentity and PhoneGroup nodes; aggregated communication edges | Dossier and entity links; Significant |
| Financial ledger | Same-day phone activity around a payment; "Also recorded on phone" on corroborated rows | Date-only ledger rows; counterparties through the reviewed identity path |
| Map | Phone layer with uncertainty; Together; places | Address dossiers for place labels |
| People and dossiers | Identities, owner decisions, collected items | Dossiers as the person record; dossier contacts for suggestions, excluding contacts copied from phones |
| Search | Message, record, people, call, email and media groups; keyword lists | The palette and header box. There is no ledger group in Search (03 D-14). |
| Saved work | Phone link types everywhere; collection export | Findings, theories, notes, tasks, labels, Timeline curation |

**Agent rules:**
- Answers are stored as agent artifacts marked as model readings. Only a person can accept them into a dossier assessment or a finding (CO-18). The agent may propose links and never adds them itself.
- **Agent visibility (Neil, 2026-11-01): "the agent should have full visibility of the phones".** The agent, chat, Workspace AI and theory analysis read phone records in full (text, names, numbers, account ids, addresses, attachments' text) through the existing model policy (no separate case setting is needed to send phone material to the AI provider). Every claim still carries its `rec://` link, its scope sentence and any clip; unconfirmed readings are still named. The per-case external-processing decision remains only for the other outbound services (embeddings, transcription, translation, image search, geocoding: plan standing decision 8). Reverse if Neil restricts it. The agent reads only the case it is asked in: phone tools take the case id and every query is scoped to it, as the existing agent's queries are (`services/agent/cypher_safety.py` refuses any graph query without the case id). A test asks the agent in one case about a phone that exists only in another case and gets "not in this case". Working across all of a person's cases is not built here and is never the default; it is recorded for the agent build phase as an option the person switches on, limited to cases they can open.
- **With the decision,** tools return text and identifiers, and the answer says that phone material was sent to the named provider.
- Today's overview, timeline and map tools say "Phone messages and calls are not in this result; 186,787 are on the phones. Use the phone tools", and agent map and table artifacts say whether phone points are included.
- An evaluation set of 30 or more questions with known answers on synthetic phones is measured before release: correct records cited and correct totals stated.
- The agent run limit of 28 tool calls is stated in the answer when it is reached.
- 02 9.8 chat retrieval follows the same rule.

### 7.2 Crossing tests (XF-), all in the cb-crossev gate unless named

| Id | Journey | Pass condition |
|---|---|---|
| XF-1 | Ledger row → "Phone activity around this payment" → Lanes and Conversations for the counterparty's linked people, the payment date ±1 day | Counts equal Conversations under the same scope. The wording is "same day" or "1 day before", never a time of day. An unlinked payee shows "This payee is not linked to a person, so the phones cannot be matched. Link it in People." Payees that exist only on payments can get a dossier. |
| XF-2 | Graph person node → "Conversations on the phones" | The node count equals the dossier panel and the Conversations total. Back restores graph selection and viewport. |
| XF-3 | Agent: "Who did A talk to the day before payment X?" | Every claim has a `rec://` link that opens the record panel; a scope sentence is present ("read N of N messages and calls on M phones that day"); a clipped result is stated; unconfirmed readings are named. |
| XF-4 | Timeline period → "What the phones did" | Lane counts equal the lens and Conversations. "No data" bands are drawn. |
| XF-5 | Dossier "On the phones" → everything about this person | Counts equal the screens they open. Collected items open their records with origin marks. (cb-screens gate) |
| XF-6 | Map area and window → phones present → their conversations | Every listed phone has a point inside the area and window. The opened count equals the Conversations total. (cb-screens gate) |
| XF-7 | Search hit → Add to finding → collection export, plus theory analysis | The export total equals the collected count. Badges carry through. Workspace AI cites the phone records with full phone visibility. |
| XF-8 | Phone contact → counterparty suggestion (phone number and email kinds) → "Open these payments" | Shown as "Suggested, not reviewed" until confirmed. No ledger row changes. |
| XF-9 | Browse Conversations → open Financial | Financial's updating answers stay on. (`followups` fixes; test in the cb-screens gate) |
| XF-10 | "Ask about these messages" from Conversations | The chat request carries the thread, scope and selected record ids, never their text without the decision |
| XF-11 | Significant layer on | Phone screens say "Phone screens show all records. 3 of 41 phone identities are significant. Show only those". The toggle's counts agree. (cb-screens gate) |
| XF-12 | Agent map artifact in a case with phones | Includes phone points, or says they are left out |

### 7.3 Rules that make it one product

- One scope bar, one count wording, one time formatter, one origin mark.
- One link vocabulary: Unclassified, Supports, Contradicts, Context.
- One keymap, one progress panel, one record panel, one **Add to…** menu.
- Back always restores place. Every crossing states what changed ("Now showing Financial for 2 linked counterparties").
- The chat side panel receives the open thread, the scope and the count of selected records.
- The Significant layer is a toggle on phone screens, never a silent narrowing.

---

## 8. Phones on their own

The first real phone case holds only phones.

- No phone screen or journey needs a ledger, other evidence or financial access.
- Lens and layer defaults follow 4.12.
- Every money part says what is absent and never shows "0 payments": the graph edge money summary, counterparty suggestions, the Day view money lane, approach 1, and "Open these payments". The wording: "No financial records in this case. Add bank statements to see payments beside the phones."
- The Financial page says "No financial evidence in this case. Add bank statements from Evidence."
- The agent overview counts phone records.
- Adding a ledger later lights up the crossings with no re-reading of phones.

**Tests,** run in a synthetic phones-only case (section 10.1) and read-only in the real one once loaded:

| Id | Test | Gate |
|---|---|---|
| SA-1 | Every phone route loads with no error, and no empty screen lacks words | cb-screens |
| SA-2 | Timeline and Map open with phone data | cb-screens |
| SA-3 | No "0 payments" anywhere; each money part shows its sentence | cb-screens (parts that exist), cb-crossev (the rest) |
| SA-4 | Graph shows communication edges with no money text | cb-crossev |
| SA-5 | Every journey whose gate has been reached completes | each gate |
| SA-6 | Collect works with no evidence row except media registered one at a time | cb-screens |
| SA-7 | Agent phone tools answer in a phones-only case with full phone visibility (XF-3 conditions). Financial tools say "No financial evidence in this case". | cb-crossev |
| SA-8 | A user with no financial access in a phones-only case sees the Timeline lens, the Map layer and Graph edges fully, with no financial refusal or blocking panel. Adding a synthetic ledger makes XF-1 and XF-8 work with no re-ingest. | cb-screens (first part), cb-crossev (second part) |

---

## 9. Learnability and support

- **First phone in a case.** The new sidebar items carry a "New" mark for 7 days. A one-time card on the Phone summary says what each phone screen is for and where phone data appears elsewhere. It can be reopened from Help.
- **Empty states that teach.** Each says what the screen is for, why it is empty and one next action. New rows in the 03 3.8 table:

  | Screen | Copy |
  |---|---|
  | Conversations, nothing selected | "Pick a thread or a person. The busiest are listed first." |
  | Filter with no matches | "No messages match these 3 filters. The date filter removed 2,140; remove it?" |
  | Needs a decision, empty | "Nothing needs a decision. New items appear when a phone is added or a reading changes." |
  | Patterns, owner unknown | "Patterns need to know whose phone C3 is. Set the owner." |

- **In-context help.** Every badge has a meaning sentence and a "Learn more" link. `?` opens the keys. Each screen header links to its guide page. The glossary covers carving, synced from another device, decoding confidence, empty placeholder, generic reading and uncertainty radius.
- **Guide.**
  - `docs/user-guide/phone-user-guide.md` is organised by the journeys, with synthetic screenshots on a light background.
  - `phone-team-checklist.md` has 12 tasks or fewer, each marked Pass, Fail, Blocked or Not run, with the rule "record what actually happened; do not pass a step just because a button could be clicked".
  - Both open from a Guide button outside the scrolling content.
- **Training case.** A synthetic case with two synthetic phones and a small synthetic ledger, for practice on fake evidence (section 10.1).
- **Report a problem.** A button on every phone screen. Reports are stored in a new Postgres table, `ui_problem_reports`, with case access rules: case members with access and admins see them. This is new scope.
  - **Structured fields:** screen id, scope as kinds and counts, the action chosen from a list, whether a refresh changes it, build id, time, last request id, viewport, and component ids of the area.
  - **Free text:** an optional "What did you expect?" box, stored in the database only. No screenshot is taken.
  - **To jobs:** the coordinator receives ids, kinds, counts and the build id only. Reports do not go through the corrections feed.
  - **Test:** payloads sent to jobs contain no case values.

---

## 10. Measuring

### 10.1 Scripted tests [S]

- **Where:** a browser on `http://104.196.62.215:5174`, signed in with the jobs login (run-rule 6). The jobs login views the financial cases and changes only the verification case `cded78d0`.
- **Data:**
  - Writes go to the verification case, loaded with synthetic phones made by extending the 01 section 12 fixture builder with invented content at real structure and scale.
  - **Phones-only runs:** cb-ux measures whether `cded78d0` holds any ledger or other dated or located evidence, and records the counts.
    - If it holds none, phones-only tests run there.
    - If it holds any, they run in a separate synthetic phones-only case once one exists and the jobs login can write to it (Neil question 1). Until then each SA test reports "not run: no phones-only case" in STATUS, and its gate is recorded as passed on the verification case with that limitation stated.
  - The training case needs the same access.
- **When:** outside 14:00 to 23:00 UTC where possible (the team's assumed working day; **estimate, not measured**), paced, serially, under `flock /mnt/owl-data/fin-wt/suite.lock`.
- **Each script asserts:**
  - The journey completes through visible controls in the stated number of actions, and by keyboard alone with visible focus.
  - Outcomes are found by role and text.
  - Every count equals the API total for the same question, and totals agree across screens.
  - Data or a worded panel appears within 2 s on every slow path (forced with a slowed network). It updates at least every 1 s, and no spinner lacks words.
  - No "Load more" appears, and every list carries its count sentence.
  - Copy works with `isSecureContext === false`, in both formats.
  - Back and reload restore filters, selection and scroll anchor.
  - There are 0 overlapping boxes at 1280×720, 1440×900 and 1920×1080, and the first work item is above the fold.
  - axe finds no serious issues, and there are no console errors.
  - Collected items open back to their record, and every review action writes one feed line.
  - Time to first useful row and time per step are recorded as measured numbers.
- **Case material in test output.**
  - Screenshots, traces, DOM dumps and full axe output come only from the verification case and synthetic cases.
  - **Runs against a real phone case** are read-only. They record numbers only: counts, timings, rule ids with counts, and failures as selector plus count. Nothing is captured.
  - Before any STATUS or commit write, the runner scans the output for strings it read from the real case (held in memory only). A match refuses the write and records "refused: case material in output".
  - A unit test proves the refusal.

### 10.2 Instrumentation [I]

- **Route timing** extends below `/cases/:id/<view>`, so phone sub-pages are no longer "other".
- **Events:** journey start, step, complete and abandon; waits over 2 s, with or without a panel; leaving before data arrived; back-and-forth between screens; searches with no result (count only); collect sizes; time per review item; whether examples were opened before a decision; suggestion acceptance per reason; second-person disagreement rate.
- **Fields:** ids, kinds, counts and milliseconds only. Never names, numbers, text, addresses, coordinates or query strings. A unit test checks every payload against the list of allowed fields.
- **Where it goes:** Loupe's own speed and activity records, shown as funnels on the admin Speed page. Nothing goes to a third party.
- **Decision events** also record the session and user agent.

### 10.3 Moderated sessions [M]

Sessions are run by a person, not by a job. cb-ux prepares each round's pack:
- task cards written as investigator goals with no hints
- consent wording
- a synthetic case with a written case story, so relevance tasks such as J-2 and Start here make sense
- a result sheet
- the analysis method

The coordinator books each round with `tell.sh at` and sets the release hold (below).

- **Who and how:** up to 5 participants per round, about 60 minutes each, in their own browser at the http address. Tasks rotate between rounds, and one new person joins per round where the team allows. Learning effects are reported.
- **Recorded per task:** success, human time, actions, errors, and the single-ease rating (1 to 7). The System Usability Scale (0 to 100) is recorded at the end.
- **Notes** hold counts and the person's words about the interface, never case content. No screen video is recorded.
- **Comprehension probes** run in every round, each scored correct or incorrect:
  - "What time and day was this sent, in which zone?"
  - "Was the phone in use here?"
  - "Is this person confirmed as the sender?"
  - "Are all messages between these two on this edge?"
  - Any misreading of time, absence or provenance becomes a top-priority follow-up whose wording fix has an [S] test.
- **Results** from fewer than about 20 people are labelled directional. They never pass or fail a job. Every finding becomes a concrete item with its own [S] regression test, in the brief of the job that owns the screen (or `followups` once that job is DONE).
- **Release hold:** a session window sets `headless/RELEASE-HOLD` with an expiry time. The batch release and `deploy-now.sh` check it and log "held until <time>". The coordinator sets and clears it, and the hold expires on its own.

| Round | When | On what |
|---|---|---|
| R0 | When cb-ux's prototype is live | Clickable prototype on synthetic phones: layout, density, combined label, time strip, From/To, Needs a decision, Add to… |
| R1 | Conversations, Phone summary, Needs a decision and Add to… live | Real phones, read by the participant |
| R2 | cb-screens and cb-pol DONE | Screens, Patterns, People |
| R3 | cb-crossev DONE | Crossings with the agent and ledger |

- **If R0 has not been held** by the time cb-screens builds a unit that R0 would inform, cb-screens builds that unit to this spec. The choices R0 would have tested are recorded in 03 as decided without investigator input, each with what reverses it, and R1 is the first observed round.
- **Reference levels** for reading results: 4 of 5 succeed on a task; median ease 5.5 or more; SUS 75 or more. Published SUS scores for phone-review tools are collected in research note 09. These are reference levels, not gates.

---

## 11. Gates

Only [S] and [I] tests gate a job. A gate that fails on measured numbers is recorded with its numbers and what reverses it (CB-INDEX rule 10).

| Gate (CB-INDEX) | Adds to the existing gate |
|---|---|
| cb-ground DONE (A→B) | The section 15 spec changes applied, 07 merged, research note 09 written |
| cb-ux DONE | Section 12.1 finish list |
| lx-collect DONE | CO-2 (API), CO-3, CO-5, CO-16 (API), CO-17 (API), CO-21; registry tests; must be live before cb-screens builds 03-3 |
| cb-capture DONE (B→C) | I-1, I-2, J-1a |
| cb-interpret DONE (C→D, D→E/F) | RQ-1 to RQ-8, U-backend, J-8a, one feed test per review action |
| cb-screens DONE (E→G) | J-1b, J-2, J-3a, J-4, J-6, J-7, J-8b, J-10a, J-11, J-12, J-13, J-13b, J-14a, J-15, J-16, J-17, UX-1 to UX-5, C-10 to C-13, MD-1, P-6 to P-8, U-5 to U-8, S-8 to S-10, G-5, G-6, T-7, E-8 to E-10, XF-5, XF-6, XF-9, XF-11, SA-1, SA-2, SA-3 (existing parts), SA-6, SA-8 (first part), CO cells for its surfaces, CO-2, CO-4, CO-6 to CO-8, CO-9a, CO-12, CO-14 to CO-17, CO-19, CO-20 |
| Gate F (cb-pol DONE) | J-5a, J-9, J-10b, POL-1, CO cells for Patterns and Lanes |
| cb-crossev DONE (G→H) | J-3b, J-5b, XF-1 to XF-4, XF-7, XF-8, XF-10, XF-12, SA-3 (rest), SA-4, SA-7, SA-8 (second part), CO-10, CO-11, CO-13, CO-18 (agent), CO cells for Graph, the agent evaluation set measured |
| cb-approaches DONE | J-5c, J-14b, the J-16 equality with approach 12, AP-1, CO-9b, CO cells for analyses |
| cb-media DONE | M-5, M-6, M-7, CO-18 (transcript) |
| J-10c | In the gate of whichever of cb-screens and cb-pol finishes second |
| Every release | A journey test that passed and now fails **on a real phone case** (read-only, counts only) blocks the release, as a data loss does. A failure only on synthetic fixtures goes to the owning job's list, or to `followups` once that job is DONE. A speed gate on time to first useful row is set only after a baseline exists (median of at least 5 paced runs outside working hours, with the spread reported) and is labelled a target until then. |

---

## 12. How it gets built

### 12.1 New jobs

**cb-ux** (starts now). No running job builds frontend components, and cb-screens cannot start until cb-interpret is DONE. Building the kit now puts it in place before the first phone screen and lets R0 run on a prototype. Build list:
- A. Extend the 01 section 12 fixture builder with invented content at real structure and scale, plus a phones-only shape and a training shape.
- B. Journey and UX tests written first, red against the fixtures, each handed to the job named in section 11.
- C. The shared kit (section 5), including semantic tokens and the phone palette, the keymap registry with `?`, the copy helper, the phone selection store, the docked record panel slot, and read-flagged progress requests. Shared screens keep every filter, action and state, and Financial tests stay green.
- D. A clickable prototype of Phone summary, Conversations, Needs a decision and Add to…, behind a switch that is off.
- E. Instrumentation (10.2).
- F. Guide, checklist, glossary, training-case content, and Report a problem (9).
- G. Session packs for R0 to R3 (10.3).
- H. The measurement of `cded78d0` for phones-only use (10.1).

**lx-collect** (starts now). Section 6.4 items 1 to 13. It is Loupe-wide: it changes dossiers, workspace, tasks, timeline and the financial report, not phone data. It must be live before cb-screens builds 03-3 and before cb-pol builds 04-U13. No running job owns these files. It takes cb-pol item K, which is removed from the cb-pol brief.

### 12.2 Order

**Starts now** (no phone data needed):
- cb-ground applies section 15 and writes research note 09.
- cb-ux items A to H on synthetic fixtures.
- lx-collect, with phone types registered and refused until resolvers exist.
- The coordinator builds the release-hold check.
- `followups` receives 4.2 items 2, 3 (app-wide), 12, 13 and 14, plus the remaining spinners.

**Waits on data or on earlier jobs:**
- cb-capture: J-1 per-stage times are measured on the first three real phones, which needs CB-INDEX question 3 answered.
- cb-interpret: reading counts per phone are measured, then targets set.
- cb-screens and cb-pol: R1 and R2 on real phones.
- cb-crossev: R3 and the agent evaluation set.
- cb-approaches and cb-media: transcription CPU speed is measured before media targets.
- Read-only real-case journey runs start once a real phone case exists.

### 12.3 Definition of done for the phone piece

- Every gate in section 11 has passed on the http address, signed in, or is recorded with its measured numbers.
- No phone screen or layer has a bare spinner, a "Load more" or an unstated limit.
- Every review screen feeds lx-corrections, tested.
- The guide and checklist are live in the app.
- Funnels are on the Speed page with a first two-week baseline.
- Every finding from every round has an owner and is built, or is reassigned.

---

## 13. Replacement of the existing phone piece

The existing phone piece is replaced. No existing phone code, screen or data model is carried forward. Only its lessons are kept, as requirements with tests.

- Its engine is removed in unit 01-1.7. Its routers, services, frontend feature (15,815 lines) and route are removed in unit 03-3, as 06 section 7 names. Each removal re-measures 0 old rows and nodes first; the count is 0 today.
- The old columns on `evidence_files` and their migrations stay as history (01 D21, 06 section 7). New code never reads them.
- The phone-number module, naming and owner inference are new code written to behaviour rules in 02 8.2, 8.5 and 8.6. Intake folder handling is written new to 01 4.3. No old function names or code paths appear in the specs.

| Lesson | Requirement | Test |
|---|---|---|
| Silent drops led to conclusions from incomplete data; "Load more ... pretty annoying" | Exact totals, no Load more, limits stated | A3 to A5, C-1 |
| "I know that #1 texted but I don't know to who" | Name (number) on both sides at every density | A2, UX-2 |
| "How that phone views the world" | The phone's names by default; combined label | A1, C-7 |
| No day, 24-hour time; the offset prompt not understood | Day plus 12-hour time on the whole Timeline; zone named in words; comprehension probe | A6, A7, T-3 |
| Combined From/To picker reverted | Sent by / Sent to / Between | C-10 |
| Bottom timeline removal reverted; "window needs to be bigger" | Resizable time strip | A15 |
| Scrubber cumbersome, infinite scroll frustrating | Density strip, Go to date, day buttons and keys | J-4 |
| "Around this time" wanted; the rail was too heavy | Around this time inside the record panel | C-12 |
| Perspective pushed to other tabs; selection kept per case | Scope bar carried and remembered; presets | XF-2, XF-4 |
| Copy missing; checks passed on localhost while users ran on http | Copy in the click or in two steps; tests assert an insecure context | A13, UX-3 |
| "At 100%" through a long tail; false "STALLED" | True-count progress; one stall rule | I-1 |
| "Unknown error"; tester on an old build | Reference id and retry; build id in reports | A16 |
| Phones processed with no number | Owner prompt after capture; owner control | J-1, P-6 |
| Merges could not be undone | Reversible identity decisions; Unlink and Split | U-2, U-8 |
| One date fix needed in five timeline hosts | One Lanes component, one formatter, one query module | T-5, J-5a |
| Duplicate collapse marked as failing | Visible "Found 3 times" plus a person's "Not a copy" decision | A14, C-13 |
| Callouts starred into the PDF; per-person summaries | Add to findings, dossiers and labels; collection export | CO-12, CO-19 |
| Asked for, never built: watch list, geofence, header threading, plain-language search, owner shown as "You", comms tally | Keyword lists on every phone; Map area selection; header threading; owner shown as "You" (03 3.3); agent phone tools; per-pair counts | XF-6, XF-3 |
| Graph search bugs on the phone graph | Phone-edge search tests | R-4 |
| 63-item checklist abandoned after item 20 | 12 or fewer task-based checks | checklist review in R1 |

---

## 14. Research base

Patterns only. Named products and their sources are in research note 09 section 1; the practice sources below are checked in note 09 section 5.

| Class of tool | Adopted | Avoided |
|---|---|---|
| Phone-review workstations and free viewers | Triage overview first; chats per person across apps; tags that feed reports | Cut-down viewers that hide deleted and source state; slow opening of large files; exports that drop data |
| Browser review portals | Several reviewers at once | Collaboration by passing files and merging later |
| Link-analysis workbenches | Narrow a subset, then send it to graph, map or timeline; one link with counts and sums | Hand-built imports; graph clutter; a steep learning curve |
| Case management | Team-visible tasks; charts that drill to source; audit log | |
| Legal review | Batches with a second-pass check; coding per message; chronology from coded items; AI with rationale and citations | Chats cut into day pieces |
| Communications-record tools | Call records and extractions in one place; frequency views | |
| OSINT capture, collaborative timelines | Starring while working; saved views | |
| Entity resolution | Resolve before linking, with transparent reasons | |
| AI assistants in these tools | Answers cited, marked and kept | Drafts that disappear; untraceable conclusions |

| Technique | Loupe feature | Journey | Source |
|---|---|---|---|
| Two-loop sensemaking | Add to… from anywhere into findings, theories and dossiers | J-12 | Pirolli & Card 2005 |
| Information foraging, recognition over recall | Scope bar, presets, saved views, keyword lists, time strip, Back restores | J-3, J-4, J-6 | Pirolli & Card 1999 |
| Progressive disclosure | Default Timeline kinds with hidden counts; "+N" badges | J-2, J-5 | NN/g |
| Response-time limits (0.1, 1, 10 s) | Progress panel, job tray, stall rule | all | Nielsen 1993 |
| Triage under volume | Phone summary verdict, coverage, Where to start | J-2 | Wilson-Kovacs 2020 |
| Telephone association matrix, frequency | Top people; Sent by / Sent to; directional from/to matrix | J-2, J-3 | UNODC analyst manual ch. 9 |
| Contact chaining, common contacts | "Who links A and B" analysis and agent tool | XF-3 | UNODC analyst manual |
| Handset or number switching | Analysis of contact sets and timing | analyses | identity de-duplication practice |
| Chronology and event charting | Timeline curation with origin marks | J-5, XF-4 | UNODC analyst manual ch. 7 |
| Pattern of life: baseline, then deviation | Pattern grid, Day view, breaks | J-5 | pattern-of-life literature |
| Co-location with uncertainty | Together, fixed vocabulary | J-10 | 04 8.4 |
| Cell-site wording | Phrase rules in location copy | J-10 | FSR-C-135 5.1.4, 6.1.2 |
| Testing an account; strategic use of evidence | Statement check from the interview | J-9 | interview research |
| Competing hypotheses; consider the opposite | Supports and Contradicts per theory; "What would contradict this?" | J-9 | Heuer |
| Key assumptions check | Undercut codes shown in "How this was found" | J-17 | CIA Tradecraft Primer 2009 |
| Source and information grading | Automatic origin mark kept apart from the investigator's grade | J-12 | College of Policing 3x5x2 |
| Investigative versus evaluative output | "Lead for enquiry" on analyses and agent answers | J-14, J-17 | FSR-GUI-0004; ISO 21043-4 |
| Lines of enquiry and disclosure record | Keyword lists attached to a theory; coverage appendix | J-13, J-14 | CPS guidance; AG Guidelines 2024 |
| Decision log, including decisions not to act | Decision history; "Not pursued: reason" | J-8, J-13 | policy-file practice |
| Critical-findings check | Second-pass sample; second-person re-check of confirmations | J-8, J-13 | FSR-C-135 8.2 |
| Bias control | Suggestions labelled; examples by kind before confirming; who confirmed what | J-7, J-8 | Sunde & Dror 2021 |
| Follow the money with timing | Phone activity around a payment, same-day wording | XF-1 | FATF guidance 2012 |
| Usability measurement | Five-person rounds, single-ease rating, SUS, time on task, comprehension probes | 10.3 | Brooke 1996; Sauro & Dumas 2009; NN/g |

**Sources:**
- UNODC *Criminal Intelligence Manual for Analysts* (2011)
- FSR-C-135 Issue 2; FSR-GUI-0004; ISO 21043-4:2025
- CPS communications evidence guidance and Disclosure Manual ch. 30; AG Guidelines on Disclosure 2024
- College of Policing intelligence and decision-making guidance
- CIA *Tradecraft Primer* (2009); Heuer, *Psychology of Intelligence Analysis*
- SWGDE 20-F-005 and 17-F-001-3.0; NIST IR 8354; ACPO Good Practice Guide v5
- FATF *Financial Investigations Guidance* (2012)
- Sunde & Dror 2021 (doi 10.1016/j.fsidi.2021.301175); Wilson-Kovacs 2020 (Exeter ORE 10871/40462)
- Pirolli & Card 1999 and 2005; Nielsen 1993; Brooke 1996; Sauro & Dumas 2009; nngroup.com

Studies of examiners and analysts are in research note 09 section 3, published usability scores for phone-review tools in section 2, the usability-method figures in section 4, and claims that could not be checked in section 7.

---

## 15. Changes to the owning specs

cb-ground applies these through its inbox. Each test id is checked as free before use.

- **03:**
  - 3.12 points to 07 section 4.
  - 3.1 rule 4: browser find is replaced by "Find in these results".
  - 3.5 gains the 4.6 states and badge priority.
  - 3.8: error copy becomes "Reference: <id>", the new empty-state rows are added, and the origin wording is fixed.
  - 3.9: Alt+J/K for day navigation with visible buttons and a "Go to date" button; Ctrl/Cmd+F finds in results; one meaning per key; confirmation over 5,000 records. Shift+J/K, `o`, `p` and `/` are kept.
  - 5.2 routes per 4.13.
  - Sections 6 to 14 per section 5.
  - 7.3 is unchanged (no owner field at intake).
  - A15 is retargeted to the time strip, and T-5 is extended.
  - The D-9 justification "matches v1's tested rule" is removed.
  - 15.5: agent links already open through the agent citation component, so the record-link opener belongs there.
  - The 16.2 heading becomes lessons only.
  - New decisions start at D-27. Section 18 (build units) is unchanged, with units added for the kit and for collect.
- **01:**
  - 4.3 is restated as behaviour rules.
  - Intake progress and the readiness card follow J-1, with the new states.
  - Replace and Retire controls.
  - A protected report creates a task.
  - The section 12 fixture builder gains invented content at scale and the phones-only and training shapes.
  - D21 stands.
- **02:**
  - 6.8: case review is case-scoped decisions; global registry review stays admin, with case corrections as proposals.
  - 8.8 gains `confirm_phone_reading`, `correct_phone_reading` and `mark_not_duplicate`, plus `reason_kind = standard` and the reason-required list.
  - Interpretation level `applied_unconfirmed`; origin wording "Mapped by the system, not yet confirmed".
  - 8.2, 8.5 and 8.6 are restated as behaviour rules with lesson tests.
  - 9.8 chat retrieval and agent tools follow 7.1, and U14 changes to match.
  - 9.9 anchors carry the mapping version set.
  - The region count is added to the response.
- **04:**
  - The Patterns route and screen.
  - The shared Lanes component (J-5a).
  - Dispute and Check again.
  - Statement checks link to interviews.
  - Snapshots go through the lx-collect registry.
  - Key dates are Workspace entries.
  - Device and sensor counts are stated per case, not corpus-wide.
  - 04-U13 depends on lx-collect.
- **05:**
  - The shared results layout and "Lead for enquiry".
  - The coverage sentence.
  - Common contacts, the directional from/to matrix and number switching, each measured first like the other approaches.
  - Incident window entry (J-5c).
  - Approach 12 feeds J-16 and CO-9b.
- **06:**
  - Units for the cb-ux kit and for lx-collect before row 31.
  - The collect unit moves after the registry.
  - Section 6 owners are unchanged.
  - Agent phone tools go in stage G.
  - Stage gates list the section 11 test ids.
- **Plan:**
  - 10.1 reads "13 checklist entries (6 pass, 6 fail, 1 with no status) plus 1 note on a filed item", matching 03 17.0.
  - Decision 1 and 10.4 item 8 read as lessons only.

---

## 16. Decisions

| # | Decision | Reverse if |
|---|---|---|
| UXD-1 | Journeys, shared rules, collect, measurement and gates live in 07. Screen rules live in the owning spec. | A job cannot find a rule it needs from its own spec |
| UXD-2 | Moderated results never pass or fail a job. They become items with [S] regression tests. | Neil asks for a human sign-off gate |
| UXD-3 | A release blocks on a journey failure only when it is reproduced on a real phone case. Synthetic failures go to the owning job or `followups`. | Synthetic-only failures are shown to have reached real users |
| UXD-4 | No speed gate until a baseline of 5 or more paced runs with its spread exists | Run-to-run spread is measured below 10% |
| UXD-5 | Routine confirmations and identity links store a labelled standard reason through `decisions.record`. Typed reasons are required for the listed actions. | An audit or court requirement asks for typed words on every confirmation |
| UXD-6 | Looks right is enabled only after examples of every kind have been viewed, and opening is recorded | Measured disagreement rates show no difference when examples were viewed |
| UXD-7 | Reading decisions from a case screen apply to that phone in that case. Global registry changes stay with an admin. | Neil decides analysts may change global mappings |
| UXD-8 | The origin wording is "Mapped by the system, not yet confirmed" | R1 probes show the wording is misread |
| UXD-9 | Exports and copies print origin marks per row and reading-state counts on the cover | Never: rule 1 |
| UXD-10 | Machine text is confirmed on use, not item by item | R2 shows the team wants a bulk machine-text queue |
| UXD-11 | All collection uses Loupe's existing dossiers, workspace entries, tasks, timeline and Significant. No phone collection store. | An item type is measured as impossible to hold, and Neil approves a new store |
| UXD-12 | Labels are Workspace notes tagged `label`, with records linked to them | R1 or R2 shows labels are needed where Workspace links cannot reach |
| UXD-13 | Review marks are task links to `phone_thread`, with scope and count at review time | Task links cannot hold the volume (measured) |
| UXD-14 | A selection over 500 records is one `phone_selection` link with a membership index. 500 matches the existing dossier link limit. | The limit changes, or per-record links are measured as fast enough |
| UXD-15 | Links store the mapping version set. Link state is worked out on display and never rewritten. | Never: rule 1 |
| UXD-16 | Interview evidence accepts registry targets beside evidence files | The interview model is replaced |
| UXD-17 | A phone file becomes an evidence row only on demand, with `source_type = phone_file`, excluded from processing jobs and embedding; the agent reads it | The external-processing decision allows it for that case |
| UXD-18 | The agent, chat, Workspace AI and theory analysis see phone records in full (no separate case setting is needed to send phone material to the AI provider) (Neil, 2026-11-01) | Neil restricts it |
| UXD-19 | Lens and layer defaults are stored per person and case at first use | R2 shows people expect them to follow case contents |
| UXD-20 | Day navigation is Alt+J/K plus buttons. Shift+J/K stays extend selection. | A browser test on http shows Alt+J/K is not received |
| UXD-21 | The first Ctrl/Cmd+F finds in results on the server; the second press goes to the browser | R1 shows people are confused by it |
| UXD-22 | Case-wide phone pages use distinct route segments | none |
| UXD-23 | The owner prompt comes after capture. There is no intake field. | 03 7.3 changes |
| UXD-24 | Report a problem is a new table with structured fields, optional free text kept in the database only, and no screenshot | R1 shows reports cannot be acted on without a picture |
| UXD-25 | Recent search queries live in sessionStorage only | none |
| UXD-26 | Thumbnails are blurred by default in criminal cases (an inference with no source) | The team turns blur off in most sessions (measured) |
| UXD-27 | No evidence-by-hypothesis matrix. Each theory has a Supports and Contradicts view. | R2 or R3 shows a matrix is wanted |
| UXD-28 | The extraction profile is called "Phone summary" | Alex prefers the old name |
| UXD-29 | Real-case test runs record counts and timings only, and writes containing case material are refused | none |
| UXD-30 | The old columns on `evidence_files` stay (01 D21) | 01 D21's own reverse condition |
| UXD-31 | Tests avoid 14:00 to 23:00 UTC (estimate, not measured) | Measured team activity shows other hours |
| UXD-32 | Saved Timeline views gain instant and zone columns, and the old columns stay | none |
| UXD-33 | The fixture builder is extended. No second generator. | none |
| UXD-34 | The Conversations rail collapses below 1440 px | R1 shows the list is needed open |
| UXD-35 | The intake stall threshold starts at 30 s and is set from measured step rates | Step rates are measured |
| UXD-36 | Reading positions are server-side for assigned reviews and in browser storage (record ids only) for casual reading | R2 shows people resume casual reading across devices |
| UXD-37 | The prototype switch is per browser (`?phone-prototype=on`, kept in local storage); Loupe has no server-side feature switch | Neil wants the preview switched per case or for everyone from the server |
| UXD-38 | The fixture builder lives at `evidence-engine/tests/phone/fixture_builder.py` (stdlib only); cb-capture extends it rather than writing a second generator | A second job needs fixtures the builder cannot express |
| UXD-39 | The training ledger is 7 single-page monthly PDF statements loaded through Evidence and Financial's own reading; the CSV copy is for tests only | Financial gains a CSV intake |
| UXD-40 | UX events are stored as `ux_event` activity rows with one allowed-field list shared by browser and server; the activity list hides them unless asked | Event volume makes the activity table slow (measure rows per day first) |
| UXD-41 | Report a problem is delivered to the coordinator by `scripts/deliver_ui_problem_reports.py` from the database queue (`delivered_at`), because the app user cannot write the coordinator's inbox | The fleet gains an app-writable channel |

---

## 17. Neil's answers (2026-11-01)

| Question | Answer |
|---|---|
| New jobs cb-ux and lx-collect, starting now | Yes to both |
| Synthetic phones-only case and training case, writable by the jobs login | Yes |
| Phone material kept from the external AI provider by default | No: "the agent should have full visibility of the phones" (section 7.1, UXD-18) |
| Moderated sessions with Alex's team, run by Neil, up to four rounds of up to five 60-minute sessions | Yes: "I love this idea" |
| cb-crossev builds the agent's read-only phone tools | Yes |
