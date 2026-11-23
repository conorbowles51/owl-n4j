# Case assistant guide

Loupe has two ways to ask questions of a case. The **agent** (**Agent** in the case sidebar) works through a question in steps, can build tables, charts and reports, and keeps a record of each run. **AI chat** (**Chat** in the case sidebar, or the chat side panel) gives a shorter answer from a search of the case. Both answer from the case's own material and cite it.

Every answer is a model reading. It cites the records it used, and Loupe checks those citations against the records. A person confirms a finding; the assistant never does.

## Ask the agent a question

Type the question in the box at the bottom of the Agent page and send it. The answer cites the records it relies on: open a citation to see the payment, message, document page or graph item behind it.

On a new conversation the page also offers **Or start a guided workflow** (see below). Above the box, **Deep investigation** and **All my cases** change how the next question runs.

***When to use it.*** Use the agent for questions that need several steps: who paid whom across accounts, what happened around a date, who owns a phone. Use AI chat for a quick lookup.

## Follow a run while it works

While the agent works, a line names the current step in plain words, with its number and the time so far, for example "Reading what step 3 found and deciding the next step · step 3 of up to 12 · 27 s so far". Below it: "Long questions can take several minutes. It keeps running if you leave this page; come back here for the answer."

- **Stop** ends the run. The question then shows "No answer: this question was stopped before it finished. Nothing already saved is lost." with **Ask again**, or **Resume run** where the run can carry on.
- If a run stops responding, the line says "This run stopped responding after" the time so far, "so it will not finish. Nothing already saved is lost." **Resume run** sends the question again and carries on from the stopped run; **Dismiss** clears the notice.
- **Investigation trail**, under the answer, lists every step the agent took, newest first, with what each step found.

AI chat shows one line while it works: "Searching the case and writing an answer · 12 s so far".

***Reading it.*** You can leave the page, reload it or open another screen. Coming back to the Agent page picks up the run that is still working.

## Steer the agent with Tools for this question

While a run works, the card **Tools for this question** lists the kinds of material the agent can read, in plain groups: Money and ledger; Phones; Documents; People and identities; Map and places; Graph queries; Case notes and theories; Tables, charts and reports; Suggestions for the case; and Always on. Each group says what it covers and where it stands:

| State | Meaning |
|---|---|
| In use · N calls | The agent has read this kind of material N times in this run |
| Chosen, not used yet | The agent picked it for this question and has not read it yet |
| Available, not chosen | The agent can use it but did not pick it |
| Off · switched off by you at step N | You switched it off; the agent stopped using it from step N |
| Always on | Asking you a question, its working notes and reading the rest of a result; it cannot be switched off |

- Switch a group off or on with its switch. The change applies from the agent's next step; the step running now finishes first.
- Type a note in the box under the groups and press **Send to the agent**, for example "Check the May 2024 statement first". The agent reads it before its next step. A note holds up to 500 characters.

***When to use it.*** Switch a group off when it leads the run away from the question, for example phones on a question about one bank account. Send a note to point the agent at a record or a period.

***Reading the answer.*** Each group you switched off is listed under **Not examined** in the answer, with the step. An answer narrowed this way says what it did not read, so it never reads as complete.

## Run a deep investigation

**Deep investigation** is a switch beside the question box. With it on, the next question runs as a deep investigation: the agent plans the work as a checklist, reads the case in full, checks every item on the list, and then writes a full report.

The screen states the cost before you send: "A deep investigation reads the case in full, checks every item on a list, and can take 15 to 40 minutes. It uses several times the model cost of a normal answer. It keeps running if you leave this page, and you can stop it and keep what it has written." The same sentence shows when you point at the switch.

When a question is broad and the switch is off, the page offers: "This is a broad question. A deep investigation works through the whole case and writes a full report." Press **Use deep investigation** to switch it on; Loupe never switches it on by itself. Asking in so many words for a deep or detailed investigation or report also runs one.

While it works, the progress line carries the checklist with true counts, for example "14 of 22 checklist items closed, 8 items open; 31 findings noted." Each item shows a tick when done, how much of it is covered ("12 of 40"), or "not done" with the reason.

The report has headed sections in a fixed order: a summary for the client, an inventory of each phone, account and document, who owns each, the contact network, a reconstruction of each incident window, flagged communications, cross-checks against documents and the ledger, items chance explains, what it means for the client, and limits and next steps. Download it as PDF, Word, HTML or PowerPoint from the buttons on the report.

***When to use it.*** Use it for a whole-case review or a report question. For a single fact, a normal question is faster and costs less. The switch is not available while **All my cases** is on, except in the Significant layer.

***Reading the report.*** Every fact sentence carries its citation. "No link found" appears only with what was searched. The assistant's own readings are labelled as its readings until a person confirms them. **Limits and next steps** says what was not done and what a person must confirm.

## Start a guided workflow

A guided workflow is a set question that the agent works through in fixed steps. A new conversation shows the list under **Or start a guided workflow**; in a conversation already under way, press **Workflows** beside the question box.

The list opens with what the case holds, as counts. Each workflow then says whether it can run here:

- **Ready: all N steps can run**
- **Partly: N of M steps can run**: the steps that cannot run are named, and each is reported as not examined.
- **Not possible on this case**, with the reasons.

Press **Use** to see the steps. Steps marked "(you do this on screen)" are yours to do. Fill in any blanks, such as a name as it appears on People or a date, and press **Start workflow**. **Show N more workflows** lists the rest.

***Reading the result.*** Results come back as proposals for you to confirm, never as conclusions. Each step that did not run is listed under **Not examined**.

## Ask in AI chat

Open **Chat** in the case sidebar, or the chat side panel on any case screen, and type a question. Chat searches the case and writes a short answer with citations. Earlier conversations are listed beside the chat.

***When to use it.*** Use chat for a quick fact or a passage. For questions that need several steps, a report or a table, use the agent.

## Check the sources behind an answer

Loupe reads every citation in a stored agent or chat answer against the record it cites.

- A sentence whose citations all fail ends with *(the cited source does not mention this)*.
- The answer ends with a **Source check** line, for example: "Source check: 18 of 21 citations support their sentence; 2 support part of it, 1 do not mention it. Code compared names, figures and dates with each cited source; 6 were read by a model (its name), not by a person."
- Under that line, each citation that does not fully support its sentence is listed with the sentence, a link to the source, its state and the reason.

| State | Meaning |
|---|---|
| supports this | The source holds what the sentence says |
| supports part of this | The source holds some of the sentence; the reason names what it lacks |
| does not mention this | The source does not hold what the sentence says |
| could not check | The source could not be read, or the answer passed its checking limit; the reason says which |

***What to do with it.*** Open each listed citation before relying on its sentence. Treat a sentence marked as not mentioned as unsupported until you find a source for it. A check by code or by a named model is never a person's confirmation.

Evidence also shows unchecked claims. In a file's panel, a notice reads "N claims drawn from this file were not checked against their text, so they are not in the graph." Someone who can edit the case can press **Check them**. The check reads each claim against its file, spends from the case's AI budget, and adds the claims that pass to the graph when it ends.

## Rate an answer

Under every agent and chat answer, **Rate this answer** offers three ratings:

- **Missed something**: the answer left out something the case holds. You can paste a link to the record that should have been found.
- **Not relevant**: the answer is about the wrong thing.
- **Too thin**: the answer is too short or too shallow for the question.

Each rating takes an optional note on what went wrong; press **Send rating**. The line then reads "Rated: Too thin. Select a rating again to withdraw it." Withdrawing keeps a record of the original rating.

***Why it matters.*** Ratings are kept with the run and are used to test and improve how the assistant searches.

## When a search finds nothing

When one of the agent's searches finds nothing, the step says why and what it did not search, for example how many payments it scanned and why none matched. Read these steps in the **Investigation trail** before treating a "none found" as an absence in the case. **Run record** under an answer lists the model, the tool calls, the cases read and anything clipped, and downloads the search strategy and "What was not examined" as CSV or PDF.

## How the agent finds payments, names and documents

The agent and AI chat search the case the way the Search box does. A ledger search finds payments by meaning and by
loose words, so a description written differently, or a word in another form, still finds the row, best match first.
A name search also finds names saved in a phone's contacts, initials and surnames. Phone notifications are read as text,
and a question about a named person also reads the messages on the phone that person owns.

## The phones around payments

When a run reads payments, it also counts what the phones hold, messages, calls or emails, in the week before each
one, and reads them before it answers. While it does, the progress line reads **Reading the phones around the
payments**. If it could not read them, the answer says the phones around those payments were not read, so a missing
message is never mistaken for proof that there was none. A follow-up about what came around named items reads the
ledger, the phones and the documents together.

## Text read from photos in a phone record

The agent's reading of a phone record includes the text read from each photo the message carries, and the transcript
of a voice note, each marked as a machine reading ("Machine-generated by ..., not yet confirmed") until a person confirms
or corrects it. Where nothing has been read yet, it says so; a person can ask for the text on the Media screen.

## Two people and their other identities

A reading of the contact between two people covers those two identities. If the same people have other identities on
the phones, such as another number or account, the agent says what those hold in the same window, and that they are
tied by names recorded on the phones, not by a person's link.

## Links in an answer

An answer cites each fact with a link to its source. A link to a payment opens the Financial page at its statement page.
A link to a graph item opens the Graph with that item selected and marked **Cited entity**. A link to a phone record
opens its panel over the page; on a phone-width screen the panel fills the screen, with Close on it. A link that names
nothing in the case is removed, and the end of the answer says how many were removed. A phone's saved names and the
agent's identity suggestions link to the records they come from.

## When an answer fails a check

Before an answer is shown, Loupe checks it against what the run read. An answer that says there are no emails, or no
contact, while the run read such records goes back to be rewritten once. If it still disagrees, the answer ends with
**Checks this answer did not pass**, naming the records it did not cite.

A deep report whose source review fails still shows the saved draft, with each line that failed a check marked
**[flagged]**, under "Saved draft text (..., version N); lines marked [flagged] failed a check". Open the draft and choose
**Resolve checks with agent** to fix them. A deep report states each absence of contact it found as a finding.

## Questions with several readings

When a question can be read more than one way and the answer can cover them all, the agent answers each reading under
its own heading instead of asking which you meant. A normal run splits the question into its parts and looks each one
up before it answers.

## Step-by-step workflows

Each workflow below opens as a tutorial: numbered steps, a picture of each screen on the demo case, and a link to the same screen in your case.

- [Ask the assistant and check its sources](#workflow=assistant). Use this when you want a quick answer from the whole case, with every source cited and checked.
- [Run a deep investigation](#workflow=deep). Use this when a question needs the whole case read and a full report, not a quick answer.
