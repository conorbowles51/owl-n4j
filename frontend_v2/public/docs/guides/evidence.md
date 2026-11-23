# Evidence guide

Evidence holds every file in the case as it came in: documents, statements, photos, recordings and phone reports. From here you upload a production, process files so Loupe can read them, follow that work, and open any file beside its text.

## What the Evidence screen is for

The screen has three parts. The folder tree on the left keeps the production's own folders. The file list in the middle shows the files in the open folder, with their size, status, the people and links found in them, and when they arrived. The panel on the right shows the file you open, and its tabs also hold Processing (the Jobs list), AI Chat and Notebook.

***Main controls.*** The toolbar holds the search box, the status and type filters, Send to Financial review, New Folder, Upload, Add phone report (folder or ZIP) and Process. Delete appears once files are chosen. Each file row has a menu at its right end with Open, Process, Pin to workspace, Add to Timeline, Add to event, Add to Dossier, Move to… and Delete.

***Choosing files.*** Tick files to choose them. A bar at the foot of the list then shows how many are chosen and offers Add to theory, Corroborate, Move to…, Process, Pin to workspace, Add to Timeline, Add to event, Add to Dossier and Clear.

## Upload files and folders

***What it does.*** Upload takes single files, a whole folder or a ZIP file. A folder keeps its structure, so the production's order survives. You can also drop files onto the list. The line above the list names the upload destination, which is the folder that is open.

***When to use it.*** Use Folder for a production that arrives as a folder tree, and ZIP file for an archive. Use Add phone report (folder or ZIP) for a phone extraction report; the whole report is read and checked against itself when it arrives.

***How to read the result.*** A large upload shows its progress in the Processing tab and can be resumed after a break. Files appear in Evidence once the whole selection is registered. One file can be at most 64 GB; a larger file is not uploaded, and the message names it.

## Find a file

***What it does.*** The search box has two scopes. Files in case finds file names. Text in case finds an exact name, phrase or number inside the text of the case's files. The status filter narrows the list to unprocessed, processing, processed or failed files; the type filter narrows it to documents, images, audio, video or data files.

***When to use it.*** Use Files in case when you know what a file is called, and Text in case when you know what it says.

***How to read the result.*** The line above the list counts the matches. "No files match these filters" means the filters hide everything; change them to see more.

## The file panel

***What it does.*** Opening a file shows its name, type, size and status at the top of the right-hand panel, with Open File, Text, Download and Theory…. Below come the panels that apply to the file: Photo data for a photo, Dates in the document, a preview, and the Details (size, when and how it was uploaded, when it was processed, and its fingerprint). A processed file adds its summary, the people, places and things found in it, its key relationships and its processing record.

***When to use it.*** Open a file to see what Loupe has read from it before you rely on it elsewhere, or to start processing it.

***How to read the result.*** Dates in the document lists the dates read from the file with the words they came from and the page. Confirm keeps a date; Correct replaces it. A corrected date keeps the date Loupe read on record beside it, and only the corrected date is used.

## Process files

***What it does.*** Processing reads a file and finds the names, dates, places and payments in it. They then appear on the graph, the timeline and the map, and in search. Choose files and press Process, or use Process in a row's menu.

***When to use it.*** Process files once they are uploaded. Start here on the case home counts the files not processed yet.

***How to read the result.*** "Processing started" means the work is queued. When audio recordings are among the files, Loupe asks first: Transcribe, then review stops after the transcripts so a person can check them; Process without review carries on to the end. A processed file shows Processed and the count of people and links found in it. A failed file shows Failed with the reason in the Jobs list.

## Files held back from processing

***What it does.*** Before processing, Loupe checks each chosen file. A file that looks like bank records is held back, because bank statements are read into the ledger under Financial, not processed as documents. The dialog names each held file and why. Process N other files sends the rest.

***When to use it.*** Use Send to ledger in the dialog for a real statement. Use Process as a document only when the file is not a statement; your name, your reason and the file check are recorded in the case's decision history.

***How to read the result.*** "Nothing was sent" means the files could not be checked; try again. A file marked Held from reading in the list has a notice in its panel saying why, with Release for reading.

## Follow the work in Jobs

***What it does.*** The Processing tab in the right-hand panel lists every upload, processing job and phone report reading, running ones first. The header counts how many run and how many wait. Each job names its step in words, such as "Finding people, places and events".

***When to use it.*** Open it after you upload or process, to see what is still being read and how long it has left. You can keep working meanwhile.

***How to read the result.*** Pause stops a job after the step it is on and keeps the work done; Resume carries on from there. Cancel stops after the current step: files that finished stay in the case, and the others stay as uploaded files with nothing from them added to the graph. A failed job says where it stopped and offers Retry. Clear Terminal removes finished and failed jobs from the list.

## Phone report readiness

***What it does.*** Each phone report you upload gets its own card in the Processing tab, "Getting <report> ready". The card walks through three steps: Checking the report, Reading records, and Checking nothing is missing. The running step shows true counts, such as records and files read so far, and the time left once Loupe has measured the pace.

***When to use it.*** Watch the card after adding a phone report. The phones in it are ready to work on when all three steps show done.

***How to read the result.*** When the reading ends, the card counts the report's files by outcome, for example how many match the report's fingerprint and how many are listed in the report but missing from the production. If a step has not changed for 30 seconds, the card says so and gives the time of the last change; the server is still on that step. Cancel asks first: it stops the reading and removes what was read so far, while the upload, its fingerprints and its evidence entry are kept and the report can be read again. A report that stopped shows the step it stopped at, a reference and Try again.

## Large videos

***What it does.*** Videos up to 64 GB are processed: Loupe takes frames from across the whole recording and writes a transcript. The file panel shows the frames, and you can step through them.

***When to use it.*** Upload long recordings as they are, within that size.

***How to read the result.*** A recording over the limit is refused with a message naming it. Nothing is processed from it; split the recording into shorter parts and upload those.

## File missing

***What it does.*** A file whose stored copy is gone from the server shows a File missing badge in the list. Its panel says when this was found. The record and everything read from it are kept, but the file cannot be opened, downloaded or processed.

***When to use it.*** When you see the badge, upload the same file again. Loupe recognises the same contents and restores the missing file.

***How to read the result.*** Once the file is back, the badge goes and Open File and Process work again.

## Photo data

***What it does.*** A photo's panel has a Photo data section: the date taken, the place and the camera, as the photo's own data records them. Each value the file lacks reads "Not in the photo's data", and a line lists what is absent. You can add an optional one-line caption of up to 200 characters.

***When to use it.*** Check it before you place a photo in time or on the map, and use the caption to say what the photo shows.

***How to read the result.*** These values come from the file and no person has checked them. A camera's clock can be wrong, so treat the date taken as the camera's claim. If the panel says the photo's own data has not been read yet, process the file to read it.

## Put files on the Timeline or in a Dossier

***What it does.*** From a row's menu, the file panel, or the bar for chosen files, three buttons put files to work. Add to Timeline puts each file on the case's Timeline with a link back to it. Add to event attaches files to an existing timeline event, which you find by name, date or type. Add to Dossier adds files to a dossier, or starts a new one; images also join the dossier's gallery.

***When to use it.*** Use Add to Timeline for dated photos and documents, Add to event when a file belongs to something already on the Timeline, and Add to Dossier to collect material about a person or company.

***How to read the result.*** Add to Timeline uses each photo's own date unless you enter a date, time or place for all the chosen files; review the entries before you add them. A changed date keeps the photo's own date visible on the entry. The receipt counts what was added, what was already there, and any file with no date, which is left out until you choose one. The original files never change.

## Unchecked claims on a file

***What it does.*** A file's panel can say how many claims drawn from it were never checked against its text. Those claims are not in the graph. Check them starts a check of every unchecked claim in the case, smallest file first; claims that pass join the graph when the check ends.

***When to use it.*** Use it when a file you rely on has unchecked claims, so its people and links can reach the graph. The check spends from the case's AI budget.

***How to read the result.*** The notice says how many unchecked claims the whole case has. Only people who can edit the case see Check them; others see who can start it. The notice goes once the file has no unchecked claims.

## The document text reader

***What it does.*** Text in the file panel opens the reader in a new tab: the original page on the left and the text Loupe holds for it on the right, page by page. Find in this document searches the text, steps through the matches, and marks the words on the page image where the page allows it.

***When to use it.*** Use it to check a reading against the page, or to quote a passage. Select words in the text and use Add to… to put the quote in a finding, a note or a dossier; each quote keeps a link back to this passage.

***How to read the result.*** A label above the text says how it was read: Stored text, or Machine reading for text read from an image of the page, with a confidence figure. "Low confidence: check against the page" asks for a look at the original before you rely on it. If the original is not on the server, only the text is shown.

## Select every file in a long list

***What it does.*** The list shows 250 files a page. Below a longer list, Select all N files chooses every file under the same folder, search and filters, across all pages.

***When to use it.*** Use it to process, move or add a whole result at once.

***How to read the result.*** A message confirms how many were chosen. If some pages could not be read, it says how many of the total were chosen; if none could be read, nothing is chosen.

## Delete and restore with Deleted items

***What it does.*** Delete moves files, or a folder with its files, to Deleted items for 30 days. They disappear from every screen, from search and from the assistant. You can also hide the people and links found only in those files; they come back with a restore. Deleted items, at the foot of the folder tree, lists everything deleted in the case, not only files, with who deleted it, when, and the days left.

***When to use it.*** Open Deleted items to bring back something deleted by mistake. Restore returns it exactly as it was, with everything attached to it.

***How to read the result.*** Only the case owner or an admin can Restore or Delete now. Delete now asks again, then removes the item for good and says what was removed and how much space was freed. If the delete dialog says files will be deleted permanently, there is no Deleted items list in this installation and the delete cannot be undone.

## Corroborate a file with a right-click

This appears only where it has been turned on for you. Right-click a file row and choose Corroborate this, or point at a row and press C. The file joins the case's Corroborate selection and the question menu opens, so you can ask how it relates to other items. The Corroborate guide explains the questions and the result.

## Theories and Corroborate

Add to theory, in the bar for chosen files, adds the files to a theory with how they bear on it: Supports, Contradicts or Context. In the file panel the same button reads Theory…. The button beside it, Corroborate (it can read Relate… in the file panel), weighs how the chosen files could be linked to each other. The Theories guide and the Corroborate guide cover both.

## Dates read from a document

***What it shows.*** A processed document's panel lists **Dates in the document**: when it was **Written**, **Signed**,
the **Period** it covers and when it was **Received**, each with the words it was read from and their page. Loupe reads
these dates by itself, first by its own rules and, where they find none, with a language model. Every such date is
marked **Read by Loupe · not confirmed**. An incident report is dated the day it was reported.

***What you do.*** **Confirm** a date that is right. **Correct** one that is wrong, enter the right date and **Save**. The
reading Loupe made stays on record beside your correction, and the corrected date is the one used. The dates also appear
on the Timeline, marked the same way until a person confirms them.

## When a send cannot start

If another task has been changing the same files for over a minute, **Process** stops with "Nothing was sent: another
task has been changing these files for over a minute. Try again in a few minutes." Nothing was sent, so try again
later. A file that the processing service stopped answering before it reached reads "Not sent: the processing service
stopped answering before this file's turn. You can process it again."
