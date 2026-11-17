# Graph guide

The Graph shows the people, companies, accounts, phones, places and payments found in the evidence, and the links between them. Use it to find who is connected to whom, how closely, and through what. The names table lists the same items as rows, for sorting, counting and changing many at once.

## What the Graph is for

***What it does.*** The Graph gathers every item read from the processed files and phone reports into one picture of the case. Each item opens to its summary, its sources and its links.

***When to use it.*** Use it to see who sits at the centre of a case, to follow a link back to the document that holds it, to find duplicate names, and to keep a set of items for a theory.

***How to read it.*** A large case can hold more items than the Graph draws at once. When that happens, a line above the Graph reads "Showing the N most connected of M items in this case." Search, or open an item's links, to reach the rest; the names table lists every item. A second line can say that some payments read from a statement are not drawn because the ledger already holds them from the same statement; the table still lists them.

## Main controls

The bar above the Graph holds, from left to right:

- ***Search box.*** Find or filter items by name (see the next section).
- ***Types.*** Choose which kinds of item to show.
- ***Zoom in, Zoom out and Fit.*** Fit puts the whole graph on screen.
- ***2D or 3D.*** Switches the main graph and the spotlight together. Drag select works in 2D only.
- ***Select by clicking and Select by dragging a box.*** Choose one item, or every item inside a box.
- ***Add an item and Link two items.*** Add an item or a link the evidence does not hold. Add an item shows only when the whole case graph is open.
- ***Save snapshot.*** Keeps the view as it is now, under a name and optional notes.
- ***Spacing of the picture.*** Line length, push apart, pull to the centre, and Name each line.
- ***Find the most connected items and groups.*** See the section of that name below.
- ***Find items that may be the same.*** See the section of that name below.
- ***Spotlight.*** Opens a second graph beside the first, holding only the items you put in it. The number on the button counts them.
- ***Deleted items.*** See the section of that name below.
- ***N hidden.*** Appears after you hide items; it shows every hidden item again.

The side panel on the right has two tabs, Details and Notebook. Collapse it with Collapse panel.

## Search and filter the graph

***What it does.*** The search box has two modes. Filter hides every item that does not match. Search finds items whose names are close to the words typed, spelling slips included. The count beside the box reads "N of M shown".

***When to use it.*** Use Filter to narrow the picture to one name or one kind of record. Use Search when the exact spelling is unknown.

***How to read the result.*** In Filter mode, the question mark beside the box explains the words you can combine: AND, OR and NOT; -word leaves a word out; quotes keep a phrase; * and ? stand for any letters. A filtered view gets its own Add this view to a theory button, so the theory records the filter you used.

## Read the details of an item

***What it does.*** Click an item to open its details in the side panel: its summary with numbered sources, its notes, its facts drawn from the evidence, its connections and its properties. Right-click an item for more: Show Details, Expand Connections, Add to Spotlight, Add to Significant, Add to Dossiers, Pin Node, Hide Node, Edit Node, Copy Key and Delete Node.

***When to use it.*** Use it to check where a name or a link comes from before relying on it.

***How to read the result.*** Facts marked AI-extracted were read from the evidence by a model; each names its source, and a person can pin the ones that matter. Where the item is also a person on the phones, a box links to their conversations on the phones, with a count.

## Expand the links of an item

***What it does.*** Expand Connections, or Show connected items in the details, adds the items linked to the ones chosen. Depth sets how many steps out to go, from 1 to 5.

***When to use it.*** Use it when the item you need is not drawn yet, or to see what sits two or three steps from a person.

***How to read the result.*** The new items join the Graph. Depth 1 or 2 is a good start; higher depths can add a great many items.

## Select several items

***What it does.*** With two or more items chosen, the side panel lists them by type and offers Merge, Compare (for exactly two), Hide All and Subgraph. The legend's Select all shown and Clear selection work on what is drawn now.

***When to use it.*** Use it to compare two names that may be one person, to clear clutter from the picture, or to keep a set for a theory.

***How to read the result.*** Subgraph and Add to spotlight put the chosen items in the spotlight beside the main graph, where you can study them apart from the rest.

## Find the most connected items

***What it does.*** Find the most connected items and groups runs four questions on the Graph: the most connected items, groups that link mostly among themselves, items that link otherwise separate groups, and the shortest routes between selected items.

***When to use it.*** Use it to find the people who hold a network together, or the one person who connects two groups that otherwise never meet.

***How to read the result.*** Each list explains its own number. For the most connected items and the items that link groups, the number ranks them: higher is more central. It is not a count of links. For groups, the number is how many items each group holds.

## Plain names for item types

***What it does.*** The legend, the type filter and the badges on each item name every kind of item in plain words, such as Financial transaction, Phone identity, Statement period or Cell tower. The legend counts each type and can select all of one type, or put all of one type in the spotlight.

***When to use it.*** Use the legend to pick out every account, or every phone, in one click.

***How to read the result.*** A count such as "12 of 40" means 12 are shown and 28 are hidden by the current filter.

## Financial transactions and transactions

***What it does.*** When a case holds both kinds, the legend says: "Financial transactions are rows of bank statements. Transactions are payments the model read from documents."

***When to use it.*** Read it before counting payments on the Graph.

***How to read the result.*** A financial transaction comes from a statement in the ledger. A transaction is a model's reading of a payment mentioned in a document, such as an invoice or a letter. The two are separate sources, so the same payment can appear in each form.

## People in contact

***What it does.*** When the case holds phones, a line above the Graph reads "People in contact: N pairs of people on the phones messaged, called or emailed each other. See who and how often". Opened, it lists each pair with their messages, calls and emails, busiest pair first. Eight pairs show at first; Show all N pairs lists every one.

***When to use it.*** Use it to see who talks to whom most, and to go straight to their messages.

***How to read the result.*** Point at a row, or tick it under Choose, to find the two people on the graph. A row that says a person "is not drawn on the graph now" means a filter or the type list hides them. Show their messages opens Conversations at the messages between the two. The panel stays open or closed the next time you open this case.

## Count contact between two dates

***What it does.*** Count only between sets a start and an end date. Count recounts every pair for those whole days. Clear dates goes back to all dates.

***When to use it.*** Use it to see who was in contact around an incident, or how contact changed from one period to the next.

***How to read the result.*** The line beside the dates says which days the counts cover, in UTC. A pair with no contact in those dates reads "No contact in these dates", and on the graph its link is dashed. The dates clear when you leave the Graph.

## Contacts of one person in each direction

***What it does.*** Show one person's contacts, each direction apart puts one person at the centre and lists everyone they were in contact with, counting what each sent the other separately.

***When to use it.*** Use it to see whether contact ran mostly one way, for example many messages out and few replies.

***How to read the result.*** Each row reads "A to B" and "B to A" with its counts, and Open these messages goes to the messages. Click a name to follow from that person; Back to returns along the trail. Show the list of pairs goes back to the pairs.

## Add pairs to a dossier theory or note

***What it does.*** Tick one or more pairs, then press Add the chosen pairs' messages to a dossier, theory or note. Each pair is kept as the set of messages and calls between the two, then you choose where to add it.

***When to use it.*** Use it to keep the contact between two people as evidence for a theory, or to put it in a person's dossier.

***How to read the result.*** The item added opens back to those same messages, and its count matches the pair's count. If a pair cannot be saved, a message says how many were saved, and nothing is added until all are.

## Find items that may be the same

***What it does.*** Find items that may be the same scans the case for pairs of items with similar names. Choose the types to scan and a similarity threshold from 50% to 100%, then press Scan.

***When to use it.*** Use it after processing a production, when the same person or company may appear under several spellings.

***How to read the result.*** Pairs are listed most alike first, each with a bar for how alike they are. The line above says how many pairs are shown and how many more fall below the threshold; lower the threshold to see those. For each pair, Compare shows the two side by side, Merge joins them, and Not a duplicate records that they are different.

## Merge items

***What it does.*** Merge joins up to 25 chosen items into one. Click a name to use it, or type another; choose the type, or let the model decide. A model combines the summaries, facts and sources of the items, keeping where each came from.

***When to use it.*** Use it when two or more items are the same person, company or account.

***How to read the result.*** The dialog shows the merge's progress and says when it is complete, or complete with warnings. The original items move to the graph's deleted items. With more than 25 chosen, the dialog says how many are left out; select those again and merge in a second step.

## Merged from

***What it does.*** An item made by a merge shows Merged from in its details: the date, who merged, and the name and key of each item it replaced.

***When to use it.*** Use it to check which names were combined before citing a merged person or account.

***How to read the result.*** "No name on record" means a replaced item had no name. "Some sources could not be removed from the graph" means the merge finished with warnings, and some of the originals may still be on the Graph.

## Deleted items on the graph

***What it does.*** Deleted items on the bar opens the graph's recycle bin. It lists every deleted item under Deleted, Merged or Evidence removed, with when, by whom, and how many of its links were kept with it. The button shows when the whole case graph is open.

***When to use it.*** Use it to bring back an item deleted by mistake, or one removed by a merge.

***How to read the result.*** Restore puts the item back. Delete permanently asks "Delete forever?" first; after that, the item cannot be brought back. Search the bin by name.

## Add to theory and Corroborate

***What it does.*** Add to theory keeps chosen items in a theory and asks whether they support it, contradict it, or are context. In an item's details the buttons read Theory and Relate. Corroborate saves the chosen items as one group and weighs how they could be linked.

***When to use it.*** Use Add to theory to keep the reason you chose items with them. Use Corroborate to test whether items that look related really are.

***How to read the result.*** The Theories guide and the Corroborate guide explain both in full.

## Lasso to corroborate

This control appears only where it has been turned on for you.

***What it does.*** Lasso to corroborate lets you draw round items on the Graph. The items inside become your selection, and the question menu opens to choose what to ask about them.

***When to use it.*** Use it to corroborate a cluster of people, phones and accounts without picking each one.

***How to read the result.*** The selection counts the items and the links between them. When the Graph shows only part of the case, a note says the lasso covers the items shown. The lasso works in 2D only.

## Phone scope on the graph

***What it does.*** Open in Graph on a phone screen brings its phones, people and dates to the Graph. A line reads "Phone scope:" with the scope, and the people and phones in it go into the spotlight. Back to Conversations returns you.

***When to use it.*** Use it to see how the people in a set of conversations connect to the rest of the case.

***How to read the result.*** The line says what the Graph cannot carry over. It shows phones, their owners, linked people and those who took part in a message or call, not numbers found only in an address book. It does not narrow by direction, kind of record or label. Dates change the contact counts only, not which people and phones are drawn.

## Phone layers on the graph

This control appears only where it has been turned on for you.

***What it does.*** With a phone scope on the Graph, a Phones control lists each phone in the case with a switch, Only this, and All. Above six phones it adds Find a phone or owner and groups the phones by owner.

***When to use it.*** Use it to add or remove phones from the scope without going back to Conversations.

***How to read the result.*** Turning a phone off or on changes the phone scope, and the spotlight follows it.

## The names table

***What it does.*** The Table lists every item in the case graph as a row, with Name, Type, Connections, Sources, Amount, Date, File Name and Location. Search with the box or press /. Choose types, choose columns, change Rows per page, and Export CSV. Add Entity adds an item.

***When to use it.*** Use it to reach items the Graph does not draw, to sort by connections or amount, or to export a list.

***How to read the result.*** The count reads "N entities", or "N of M entities" when a search or type filter narrows them. Click a row to open its details in the side panel. Ctrl-click adds a row to the ticked rows, and Shift-click ticks a run.

## Explore relationships in the table

***What it does.*** A row with links shows Explore N relationships beside its name. It lists the items linked to that row, with a Relationship column naming each link.

***When to use it.*** Use it to step through a person's links as a list, one level at a time.

***How to read the result.*** The trail above the table shows each step you took; click one to go back, or Back to all to leave. The count reads "N relationships of" the item you started from.

## Change many rows at once

***What it does.*** Tick rows to get Merge, Bulk Edit, Delete and Clear selection, and Add to Significant or Remove from Significant.

***When to use it.*** Use Bulk Edit to set one property on many items, Merge to join duplicates found in a sorted list, and Delete to clear wrong items.

***How to read the result.*** Merge takes up to 25 rows; with more ticked, the bar says how many are left out. Delete asks first and moves the rows to the graph's deleted items, where they can be restored.
