# The demo case: "Demo: State v. Mateo Ruiz (synthetic)"

The demo case (`b75f3f2c-ffa1-4260-8fe9-6f5db4e9d4df`, `CASES.demo` in `frontend_v2/journeys/lib.mjs`) is one invented
defence investigation that uses every part of Loupe: six phones, four bank accounts, the State's discovery documents,
and the work an investigator builds on them (dossiers, tasks, a deadline, notes, theories, drafted interview claims,
agent questions). It is the primary test environment: a live check that needs data across modules runs here. The
older check cases (Verification, Phones-only, Phone training) keep their recorded walks.

Everything in it is invented: people, businesses, banks, addresses, numbers (555-01xx), e-mail (example.com/.org/.net)
and plates. Every document page is headed "SYNTHETIC — INVENTED FOR TESTING — NOT EVIDENCE". It is safe to show to
lawyers and testers. The 14 real phones stay in their own restricted cases; nothing invented sits beside them.

Members: the jobs login (owner) and two Owl editors. Nobody else.

## The story, in one paragraph

Over five Friday nights (15 March, 12 April, 3 May, 17 May, 31 May 2024) a crew stole pallets of tools and televisions
from Unit 7 of Brightwater Logistics. The State charges Mateo Ruiz, who owns Ruiz Auto & Tire, as the fence who stored
the goods in bay 4 of his garage. Its evidence: a prepaid phone found in the glovebox of Mateo's tow truck, the proffer
of the cooperator Travis Kell, the night guard Lena Marsh's account of "a white tow truck with RUIZ on the door",
monthly $650 payments from Kell to the garage, and a cell-site opinion. The records show Kell ran the thefts with
Desmond Okafor, paid Marsh after each night, stored the goods in a unit rented in his girlfriend Brianna Cole's name and
sold them through Gary Penn's shop. The $650 is bay rent from October 2023, and the prepaid phone was Kell's: it entered
the tow truck on 8 June, when Mateo towed Kell's car.

The answer key, with every planted fact, trap and decoy, the files that carry it and the modules that should show it, is
`evidence-engine/tests/phone/planted-truths.json`. Read it before judging what a screen shows.

## Rebuilding the bytes

```
python3 evidence-engine/tests/phone/fixture_builder.py demo <out>
```

About 2 seconds, 5 MB. The same call gives the same bytes (the voice note needs ffmpeg with flite; photos and the scanned
statement need Pillow). Layout: `<out>/phones/PH1..PH6` (phone report folders), `<out>/statements/{kell,shop,mateo}`
(monthly PDF statements), `<out>/statements/state-exhibits` (Kell's April statement again, as the State's exhibit),
`<out>/statements/penn` (CSV), `<out>/documents` (police reports, warrant, inventory, proffer, interview, scanned
statement, cell-site report, badge log, lease, rental agreement, tow invoices, discharge paper, listings, discovery index,
HR e-mail).

`evidence-engine/tests/phone/test_demo_case.py` checks that every answer-key string is in the bytes, that the decoy
strings are absent, that every value is invented and that the build is deterministic.

### Adding a name

Every person, business and place name is listed in `demo_case.py` (`INVENTED_NAMES`, `INVENTED_PLACES`) and recorded in
`demo-name-check.json` with its live-case and map counts. The test fails when a name is added without a fresh check.
The check counts matches (never prints values) in the live Postgres name columns and Neo4j node names, and searches
OpenStreetMap's Nominatim (US) for the name: the box runs no Nominatim of its own. A name with any hit is renamed.

## Loading it (only through the app's own paths)

1. Phones, one at a time:

   ```
   cd frontend_v2
   node journeys/live-phone-upload.mjs --kind folder --path <out>/phones/PH1 --shots <dir> --label PH1 --case demo
   ```

   A stopped reading is retried with the card's "Try again" (`POST /api/evidence/engine/jobs/<job>/resume`).
2. Documents and statements, each folder through the Evidence page's Upload > Folder:

   ```
   node journeys/live-demo-upload.mjs --path <out>/documents --out <dir>/documents.json
   node journeys/live-demo-upload.mjs --path <out>/statements --out <dir>/statements.json
   ```

   Uploads do not start processing; select the files and Process (the API form is
   `POST /api/evidence/process/background {"case_id", "file_ids"}`).
3. The person-built items (dossiers, tasks, deadline, notes, theories, pins, the proffer interview and its drafted claims):
   `node journeys/live-demo-seed.mjs` (see the script head). Each is made through the app's routes by the jobs login and
   marked as a seed entry. Drafted claims stay "Drafted by <model>, not confirmed"; nothing is confirmed by a script.

Releases pause scripted uploads for about two minutes; a paused upload is resumed by the same command.

## Walking it

```
node journeys/live-demo-key.mjs --out <dir>/walk.json
```

The walk signs in once over plain http, reads each answer-key entry from the modules that should show it and scores it
found, missed or wrong link (a link to a decoy is a defect, not noise), then asks the agent the answer key's questions
and scores each answer against its expected words and citations. It prints one table per module. It is never tuned to
pass: a miss stays a miss until the product finds it.

Re-run the walk after a release to find cross-module regressions: compare its table with the last one recorded in
`headless/LX-DEMO-STATUS.md`.

## Using it from another job

- Read from it freely; write only through the app's routes, and undo through the app's own Undo.
- Do not upload other material into it: the answer key describes exactly what it holds.
- A new planted fact goes into the builder, the answer key and the walk together, with a test.
