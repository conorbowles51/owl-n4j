# The check-case seed

The Phones-only check case (`4aa79795-1076-4c75-985f-784936abb71f`) holds one extra synthetic phone, labelled C7 and shown as
"Phone 7", so a live check can walk three things no other check case can: AI drafting of a statement, a routine place, and a
search group over 500 hits. Everything in it is invented by `evidence-engine/tests/phone/fixture_builder.py`.

## What it holds

| Purpose | Content | Measured live |
|---|---|---|
| Search group over 500 | one WhatsApp conversation of 640 messages, each holding the word `lantern` | group `lantern` 640; freezes as one selection of 640 |
| Statement drafting | one Signal conversation of 8 lines, a person's account of 4 to 7 June 2024, on 12 June 2024 | 6 drafted claims from `deepseek-v4-pro` in 10 s |
| Routine place | 8 half-hourly positions from 20:00 on each of 21 days from 20 May 2024, each with GPS accuracy 12 m | Place 1: 21 stays on 21 days, within 27 m |

The report's other records come from the builder's usual shape (`like="P13"`, scale 0.01): 1,093 messages, 197 positioned locations, 45 attached files.

## Rebuilding it

1. Build the report:

   ```
   python3 evidence-engine/tests/phone/fixture_builder.py check-seed <out>
   ```

   The same call gives the same bytes. The report folder is `<out>/C7`.

2. Upload it through the app as a phone report folder:

   ```
   cd frontend_v2
   node journeys/live-phone-upload.mjs --kind folder --path <out>/C7 --shots <dir> --label c7 --case phonesOnly
   ```

   The conversations and thread documents appear within a minute or two, the positions after the next phone sweep. A second
   upload of the same folder is refused as already in the case.

3. Add the interview on the dossier "Synthetic witness (cb-pol test)", linking the conversation's thread document:

   ```
   node journeys/live-check-seed.mjs interview <dossier id> "Phone 7 · Signal · Orrin" <dir>
   ```

## Walking it

| Check | Command |
|---|---|
| AI drafting, ending on a drafted row | `node journeys/live-check-seed.mjs draft <phone id> <dossier id> <dir>` |
| Routine place, on Places over time and in the statement form | `node journeys/live-check-seed.mjs routine <phone id> <dir>` |
| The whole result of a search, over 500 | `node journeys/live-identities.mjs --shots <dir> --only e --term lantern` |

Statement drafting runs on the `statement_claim_drafting` workload, DeepSeek by default, and needs no OpenAI credit. Each `draft`
run spends one model call and adds its claims again. Drafted rows stay "Drafted by <model>, not confirmed" until a person
confirms them, and the walk never confirms one.

## Effect on other checks

The financial gate does not read this case: it holds no statements, so the ledger and review-queue lines stay as they are. Counts
that do read it include this phone: Phones-only holds 6 active phones, 114 conversations and 1,979 messages and calls, and its
message search reads `555` 1,430, `the` 1,009, `and` 145.
