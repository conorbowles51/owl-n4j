# Phone user guide

This guide explains how to work with phone reports in Loupe: adding a phone, reading what it holds, deciding who is who, checking the system's readings, and putting what you find into dossiers, findings and the Timeline.

**Updated: 17 November 2026.** Each task below ends with an **Available** line. It says whether the task can be done in this build of Loupe, in the preview only, or not yet. Use the **Team checklist** for a short first test, and the **Glossary** for the meaning of every mark you see on a phone screen.

Screenshots and examples use invented phones and invented people only.

## Contents

1. [What is in this build](#what-is-in-this-build)
2. [How phone screens fit into a case](#how-phone-screens-fit-into-a-case)
3. [Marks, times and counts](#marks-times-and-counts)
4. [Keys](#keys)
5. [Add a phone and know it arrived whole](#add-a-phone-and-know-it-arrived-whole)
6. [First look at a phone](#first-look-at-a-phone)
7. [Everything with one person, or between two](#everything-with-one-person-or-between-two)
8. [Read a conversation around a date](#read-a-conversation-around-a-date)
9. [The window around a moment, across phones](#the-window-around-a-moment-across-phones)
10. [Search everything and read the hit in context](#search-everything-and-read-the-hit-in-context)
11. [Who is who: link identities and set owners](#who-is-who-link-identities-and-set-owners)
12. [Check the system's readings](#check-the-systems-readings)
13. [Test a statement against the phones](#test-a-statement-against-the-phones)
14. [Where was the phone, and were two people together](#where-was-the-phone-and-were-two-people-together)
15. [Find deleted or concealed material](#find-deleted-or-concealed-material)
16. [Build the case while reading](#build-the-case-while-reading)
17. [Share the review and know what is left](#share-the-review-and-know-what-is-left)
18. [Export for counsel](#export-for-counsel)
19. [Resume and hand over](#resume-and-hand-over)
20. [Compare phones for a person or a pair](#compare-phones-for-a-person-or-a-pair)
21. [Explain a finding](#explain-a-finding)
22. [Follow the readiness card while a phone is read](#follow-the-readiness-card-while-a-phone-is-read)
23. [See the database row behind a record](#see-the-database-row-behind-a-record)
24. [Read a phone again with an independent tool](#read-a-phone-again-with-an-independent-tool)
25. [Switch phones on and off](#switch-phones-on-and-off)
26. [See where phones were together](#see-where-phones-were-together)
27. [Report a problem](#report-a-problem)
28. [A list for each record type](#a-list-for-each-record-type)
29. [The training case](#the-training-case)

## What is in this build

| Part | Available |
|---|---|
| Phone preview: Phone summary, Conversations, Needs a decision and Add to… on invented phones | Preview only, when the preview switch is on for your browser |
| This guide, the team checklist and the glossary | Yes |
| Report a problem on phone screens | Yes |
| Adding a real phone report to a case | Not yet |
| Phone summary, Conversations, Search, People, Map, Patterns and Export on real phones | Not yet |

**Turning the preview on.** Add `?phone-prototype=on` to the end of any case address and press Enter. A **Phones (prototype)** item appears in the left sidebar of that case. Add `?phone-prototype=off` to turn it off again. The switch is kept in this browser only and changes nothing in the case. The preview shows invented phones, never the case's own evidence, and anything you add from it stays in the preview.

## How phone screens fit into a case

Phones are part of the case, not a separate tool. Phone records appear in the same dossiers, findings, theories, notes, Timeline, Map and Graph as everything else, each with a link back to the record it came from.

- **Phones** in the left sidebar lists every phone in the case. Each phone has a **Phone summary**, its first page.
- **Conversations** shows messages and calls from one phone or from all phones together.
- **Needs a decision** lists what a person must confirm or set: owners, time zones, and the system's readings.
- A person's dossier has an **On the phones** panel with every number and account linked to them.
- The **scope bar** at the top of each phone screen says, in words, what you are looking at: which people, which phones, which dates. Copy its address to send the same view to a colleague.

- The strip above each screen of a phone case holds **Guide**, which opens this guide at that screen's part, **Keys**, which lists the keys for the screen (or press `?`), and **Jobs**, which lists every long job with true counts and time left. The list comes from the server, so a reload keeps it. A finished job gives a notice with a link; a stopped one says why.
- **Help** in the sidebar reopens the card that says what each phone screen is for.

When a case holds only phones, every phone screen works on its own: no ledger or other evidence is needed.

## Marks, times and counts

- **Origin marks.** A value the system read but no person has checked carries the mark **Mapped by the system, not yet confirmed**. Text a model produced, such as a transcript, carries **Machine-generated**. A checked value shows who confirmed it and when. A corrected value shows the original beside it; only the corrected value is searched, counted and exported. Every mark has a **Learn more** link to the Glossary.
- **Times** always name their zone: "Tuesday 4 March, 14:05 Eastern time (UTC-5)". When a phone did not record its zone, times show in the case zone and say so.
- **No data** is never the same as no activity. A period with no records is drawn as **No data**, apart from quiet periods.
- **Counts** are exact. Every list says how many items it holds, for example "2,140 messages and 96 calls between A and B on 3 phones". Nothing is cut off without saying so. When a phone is still being read, counts carry "(so far)".
- **Waiting.** Anything that takes more than a moment shows a panel in words with progress and time left. If a step stops, the panel says which step and offers Try again.

## Keys

Press `?` on any phone screen to see every key that works there.

| Key | What it does |
|---|---|
| `j` / `k` | Next or previous row |
| Space | Select or clear the current row |
| Shift+J / Shift+K | Extend the selection down or up |
| Ctrl+A (Cmd+A on a Mac) | Select the whole filtered total |
| `r` | Open the record panel for the current row |
| `c` then `d`, `w`, `n`, `t` or `l` | Add to a dossier, finding or theory, note, the Timeline, or a label |
| `g` | Go to a date |
| `a` | Around this time |
| `y` / `x` / `s` | Looks right, Not right, Skip (on Needs a decision) |
| `m` | Mark the thread reviewed |
| Escape | Close the panel or menu |

## Add a phone and know it arrived whole

1. Open **Evidence** and choose **Add phone report (folder or ZIP)**.
2. Pick the folder. Loupe checks every file before sending and shows progress with time left.
3. One card lists each stage in words with true counts: checking the report, reading records, checking nothing is missing, reading messages and calls, building case views, making it searchable, making thumbnails. You can leave the page; the card also appears in the case's attention feed.
4. When the card says **Conversations are ready**, open the Phone summary.

If the report lists more records than were read, the phone is **held** until a person accepts the difference with a reason or keeps it held. A newer report of the same phone offers **Replace the older one** or **Keep both**.

**Available:** not yet.

## First look at a phone

The **Phone summary** opens with one line saying what was read: how many records, the period covered, how many apps, what could not be decoded, and how many things need a decision. Below it:

- **Needs a decision**: owner, time zone, times with no offset, and readings to check, each with its control in place.
- **Coverage by month**, with **No data** kept apart from quiet months.
- **Top people** by contact, with message and call counts. Every number opens the matching filtered screen.
- Deleted and recovered counts, and files missing.
- **Where to start**: suggestions worked out from the counts, labelled as suggestions.

If no owner number was found, the summary says so and offers **Set the owner**. Person-level views stay off until an owner is set.

**Available:** preview only (Phone summary on invented phones).

## A list for each record type

Every count on the Phone summary opens the list it counts. Under **What Loupe reads**, the number in **Records** opens the records that stand on their own, and the number in **Inside other records** opens the records held inside another record, such as a number inside a contact. The list states its exact total. Use the filters above it for the phone, the dates, deleted records and copies. A record with no time cannot match a date, so the line under the list says how many it left out.

Select a record's name to open it. A message or call opens in Conversations at that record, among its thread; anything else opens the record panel beside the list. Passwords and card numbers stay hidden until you press **Reveal** in the record panel.

Some reports list a copy of a record from another source under the record itself. The list marks these **Copy from another source**. Where a copy repeats the record, the timeline, the activity counts and the approaches count that fact once. The copy stays in the list and in search.

**Available:** yes.

## Everything with one person, or between two

1. Start from a dossier's **On the phones** panel, from a person on the Phone summary, or from a search hit.
2. The scope bar reads, for example, "A (3 numbers, 2 accounts) on 4 of 14 phones".
3. Choose **Between A and B**, **Sent by A**, **Sent to A** or **Involving A**.
4. **All channels** merges texts, calls and app messages into one stream, with an app and phone chip on each row.
5. Read with `j` and `k`. Press `r` for the record panel.

"Include this person's other numbers and accounts" is off by default, and its effect is always shown before you turn it on. Numbers that may belong to the same person are offered as suggestions to review; nothing is merged without a person deciding.

**Available:** preview only (Conversations on invented phones).

## Read a conversation around a date

1. The **time strip** under the stream shows how many messages fall on each day.
2. Click a day, or press `g` to go to a date. The day header names the day and the zone.
3. Press `a` for **Around this time**: the same people on other apps and phones, the nearest located records, and same-day case events and payments, each counted.

Messages with no time are listed at the end and counted.

**Available:** preview only (time strip on invented phones).

## The window around a moment, across phones

Open **the window around this** from a record or a key date. One lane per phone, a lane for case events and, when the case has a ledger, a money lane. Payments sit on their day, never at a time of day. Choose a window of 1, 6 or 24 hours either side.

**Available:** not yet.

## Search everything and read the hit in context

Press Ctrl+K (Cmd+K on a Mac). Results are grouped with exact totals. A message hit opens the whole conversation at that message, with matches highlighted. **Back to results** restores your search and place.

**Available:** not yet.

## Who is who: link identities and set owners

**Needs a decision**, then **People suggestions**, steps through suggestions one at a time. Each shows the name saved on each phone, the reasons, and example records for every reason. A suggestion never rests on a name alone.

- `y` **Link**, `x` **Not the same person**, `s` Skip.
- **Unlink** and **Split** show their effect first, need a reason, and can be reversed from the dossier history.

**Available:** not yet.

## Check the system's readings

A **reading** is how Loupe interprets a record, for example which field is the sender. Until a person checks it, every value that relies on it carries **Mapped by the system, not yet confirmed**.

1. Open **Needs a decision**. Readings are listed by how many records they affect, each as a plain sentence.
2. Open every kind of example. **Looks right** stays unavailable until each kind has been shown.
3. **Looks right** (`y`) records your confirmation under your name with a standard reason.
4. **Not right** (`x`) offers plain corrections. The correction applies to this phone in this case, and the original stays visible.
5. **Skip** (`s`) moves on without deciding.

**Available:** preview only (Needs a decision on invented phones; decisions are not saved).

## Test a statement against the phones

Enter each claim beside the statement's own words. Loupe checks each claim against the phones and groups what it finds as supports, undercuts and context, with exact counts, and lists searches not yet run. A claim drafted by a model is marked as drafted and is not used until each field is confirmed by a person.

**Available:** yes, on **Patterns** under **Check a statement**.

## Where was the phone, and were two people together

Located records are drawn with their **uncertainty radius**. A point with no radius is dashed and labelled **Accuracy not recorded**. **Together** answers compatible, separated or undetermined for each episode, with the radius it assumed. A broad overlap is never called together.

**Available:** yes for positions: **Places** lists each one with its accuracy, or **Accuracy not recorded**. Whether phones were together appears only where it has been turned on for you; see **See where phones were together**.

## Find deleted or concealed material

State filters cover deleted, in trash, recovered by carving, synced from another device, and unreadable. Each can be included, excluded or shown alone. A deleted row reads "Deleted at some time before the extraction"; the report does not say when.

**Available:** not yet.

## Build the case while reading

1. Select rows: Space, Shift+click, Shift+J/K, or Ctrl+A for the whole filtered total.
2. Press `c` (or choose **Add to…**), then `d` dossier, `w` finding or theory, `n` note, `t` Timeline, `l` label.
3. Recent targets come first; a linked person's dossier is offered first.
4. The reply says what happened: "Added 412 messages to [finding]. 3 were already there." Rows then show where they are used.

Adding more than 5,000 records by key asks first. Where a target takes 5,000 at a time, Loupe adds in parts and says so; nothing is cut off.

**Available:** preview only (adds stay in the preview).

## Share the review and know what is left

Split a saved view into review tasks. Reviewers mark threads reviewed (`m`), recording who, when and how many records. Every screen shows what is not yet reviewed, and a thread that gained records after review counts as partly reviewed.

**Available:** not yet.

## Export for counsel

The export dialog states the scope in words, and its cover states how many rows rely on readings not yet confirmed. Each row carries its origin mark, and a corrected row prints the original beside the corrected value.

**Available:** not yet.

## Resume and hand over

**Continue reading** lists threads you opened and did not finish, with your place. **Since you last looked** counts what changed. **Hand over** reassigns a review task with a note of positions and open items.

**Available:** not yet.

## Compare phones for a person or a pair

Two columns, one per phone, aligned by matching message, with counts on both, only on one, and only on the other.

**Available:** not yet.

## Compare two phones, or two extractions of one

Two phone analyses compare a pair. **Who used which phone** shows the numbers, SIMs, accounts and networks two phones share, how often each was used while the other was not, whether they were together or apart and used while apart, and signs of more than one user. **Two extractions of one phone** shows whether two extractions are of one device, and what is in one and not the other, deleted between them, or new. Open them from Phone analyses and press **Run**; a next-steps card follows with what to do with the differences.

## Explain a finding

Every finding that holds phone records shows **How this was found**: the scope and searches behind it, the decisions and readings it relies on with their state, and whether it is a **Lead for enquiry** or a **Result for report**. Nothing in it is typed by hand.

**Available:** not yet.

## Follow the readiness card while a phone is read

After you add a phone report in **Evidence**, a card named **Getting [file name] ready** follows it until it can be used. It lists three steps in words: **Checking the report**, **Reading records** and **Checking nothing is missing**. The step in progress gives true counts, such as how many records and files are read so far or which entry of the report is being compared, and the time left once Loupe has measured this step's pace.

- **Pause** pauses the reading. **Resume** carries on from there.
- If nothing changes for 30 seconds, the card says so and gives the time of the last change. The reading carries on; this tells you it is slow, not that it failed.
- If the reading stops, the card names the step where it stopped and gives a reference. **Try again** restarts it where that is possible.
- **Cancel** first tells you what it keeps: **Cancel stops the reading. The upload, its fingerprints and its evidence entry are kept, and the report can be read again. What was read so far is removed.** Choose **Cancel the reading** or **Keep reading**.

When the card finishes, it counts the report's files by outcome: how many match the report's fingerprint, how many the report lists but the production does not hold, how many differ in size, and so on. Those counts tell you, before you rely on the phone, whether the production holds everything the report describes. **Clear** removes a finished card from the list.

**Available:** yes.

## See the database row behind a record

Many phone records come from an app's own database on the phone. At the foot of the record panel, the **Source database** part lets you check a record against that database, not only against the report's summary of it.

1. Open a record from its list. The record panel opens beside the list.
2. Select **Open source row**, or **Open source database** when the report does not name a row. Loupe copies the app database and opens the copy read-only, so nothing in the production changes.
3. Read what the report says: which table the record came from and at which position in the file. Below that, Loupe names the row holding that position, lists its columns with their values as stored, and shows the bytes at that position as they are.
4. Open **Tables in this database** to browse any table, 500 rows at a time.

When the database cannot be shown, the panel says why and lists the files it looked for with what happened to each. Use the row when a reading looks wrong or someone questions it: it shows exactly what the phone held.

**Available:** yes.

## Read a phone again with an independent tool

**Read again by an independent tool**, under **Analyses**, reads each phone a second time with an open-source tool: ALEAPP for Android phones, iLEAPP for iPhones. The tool reads only the files whose fingerprints match the report. Loupe then compares its reading with the report's records. A second reading made separately from the report shows where the report may have missed, added or changed records.

1. Under **Read each phone again**, select **Read again with ALEAPP** or **Read again with iLEAPP** for a phone. A phone whose operating system the report does not state shows **No tool for this operating system**. Phones are read one at a time, and each line says when its reading finished and how many files it read.
2. When the phones are read, press **Run** to compare.
3. Read the results by tab: **Totals differ**, **Only the tool read**, **Only in the report**, **Times differ**, **Content differs**, **Read the same** and **Not compared**. Text messages, calls, WhatsApp messages, contacts and web history are compared.

A record only the tool read may be one the report did not decode, or a deleted row. A time that differs gives both times as written. The tool's readings stay the tool's, named with its version: they never change or join the report's records. A record panel shows the tool's reading beside the record under **Read again by an independent tool**.

**Available:** yes.

## Switch phones on and off

On a screen that shows more than one phone, such as the Map, Conversations, the phone view of the Timeline, Places, Media and the phone analyses, the **Phones** row lists every phone in the case with its label, its owner and its count on this screen. Untick a phone to take it off. **Only this** keeps one phone; **All** brings every phone back. With more than 6 phones, the row offers **Find a phone or owner** and groups the phones by owner, with **No owner named** last.

A phone that is off is left out of what the screen shows and out of its counts, and the line under the row says so, for example **3 of 5 phones are on. The 2 off are not drawn or counted.** The choice is kept in the page address, so a reload or a copied address keeps it.

On the Map, **Show routes** joins each phone's positions in time order. The line beside it counts the moves shown and the gaps over 2 hours left unjoined, so a long gap never reads as a journey. Positions with no time are counted and left out of the routes.

A page that belongs to one phone says **This page shows one phone. Add other phones in Conversations, Timeline or Map.** Each link opens that screen with this phone on, ready to switch on others.

## See where phones were together

This part appears only where it has been turned on for you, and with phone switching above.

When two to eight phones are on, Loupe looks for times they were in the same place, people they share and messages passed from one to the other.

- **Map:** **Show where the phones were together** lists each meeting: the phones, when, how many 15-minute slots they shared in the same 550 m square, and the best accuracy their positions state, or that accuracy was not stated. **Show** marks the meeting on the map. A meeting in a place where many other phones also were is marked **Busy place: weak**, because a crowded place says little about two people meeting.
- **Timeline:** **Shared moments** counts the times the chosen phones were in the same place over the period shown, and lists each one.
- **Conversations:** **People on more than one of these phones** lists each shared contact with its count on each phone. **Relay chains** lists a person who dealt with one phone and then another within minutes, with the time.

Each line has **Open the [number] records** and **Corroborate**, so you can read the records behind it or weigh it with other material. **What was searched** lists what Loupe looked at and what was out of reach, so a part with nothing found tells you what was searched, not that nothing happened. With more than eight phones on, Loupe asks you to switch some off.

**Available:** where it has been turned on for you.

## Report a problem

Every phone screen has **Report a problem** at the top right.

1. Choose what you were doing from the list, and whether refreshing the page changes it.
2. Optionally say what you expected.
3. Select **Send report**.

Loupe records the screen, the size of what was in view as counts, the build, the time and the window size. No screenshot is taken. What you type stays in this case's records and is visible only to people with access to the case and to administrators. The team is told only that a report was made, on which screen and build, never what you typed or what was on screen.

## The training case

The training case holds two invented phones and a small invented ledger, so you can practise without real evidence. Every person, number and message in it is made up. Ask the case owner for access.

## Words also on another phone

Where the newer Corroborate is turned on, Conversations offers **Mark what also appears elsewhere**. A message whose words
appear on other phones is marked **Also elsewhere**, with how many messages, phones and dates hold them; a stock phrase
is shown but counted for nothing. The **Also elsewhere** panel lists those words, messages deleted on one phone and kept on
another, and files and pictures shared across phones. The Corroborate guide explains each part.

## Step-by-step workflows

Each workflow below opens as a tutorial: numbered steps, a picture of each screen on the demo case, and a link to the same screen in your case.

- [Who was in contact with whom?](#workflow=contact). Use this when you need to know who messaged or called whom, how often, and under which names.
- [Check a phone report is complete](#workflow=phone-check). Use this before you rely on a phone: compare it with a second, independent reading and look at the rows behind a record.
- [Last proof of life](#workflow=last-proof-of-life). Use this when a person is missing or dead: find the last thing they did themselves, apart from what their phone did alone.
- [Procurement kickbacks](#workflow=procurement-kickbacks). Use this when a contract may have been bought: follow meeting, award, payment and cash between two people.
- [County lines](#workflow=county-lines). Use this when you need who ran a deal line over which periods, and the debt or threat messages beside the supply.
- [Coercive control](#workflow=coercive-control). Use this when one person may control another's money and phone: list the bank-control events and monitoring apps by date.
- [Human trafficking](#workflow=human-trafficking). Use this when you need who could operate a victim's phone and accounts, and where the money went.
- [Embezzlement](#workflow=embezzlement). Use this when a phone shows accounts or cards the books do not, or statement months are missing.
