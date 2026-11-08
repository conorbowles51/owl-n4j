# Customer data: export, offboarding, backup expiry and two-person deletion

For the operator of a Loupe instance, working as root on its server, and a second named person where a step says so.
Stores and sizes are in `docs/backup-inventory.md`; restore steps are in `docs/backup-restore.md`.

An item marked **Missing** does not exist today. The step beside it says what is done instead.

## Customer export

What a customer can take out of the app today, signed in as a member of the case:

| What | Where in the app | Route |
|---|---|---|
| An original evidence file | Evidence, open the file, Download | `GET /api/evidence/{id}/file` |
| Statements and ledger | Financial, Export | `POST /api/financial/.../ledger-export`, `GET /api/financial/export/pdf` |
| Reviewer judgements | Financial, Judgements | `GET /api/financial/judgements/export` |
| Timeline | Timeline, Export | `POST /api/timeline/export` |
| Phone records | Phones, Export | `POST /api/phones/exports` |
| Agent run record and artefacts | Agent, Export | `GET /api/agent/runs/{id}/record/export` |

1. List the customer's cases and agree the list with the customer in writing.
2. For each case, take the whole-case export below, or each export above as a member of the case.
3. Record each file's name, size and `sha256sum` in a list that goes to the customer with the files.
4. Hand the files over by the route agreed with the customer. Each exported file is one case's material, including anything
   privileged or restricted in it.

**Whole-case export.** The case owner or a super admin builds one verified package of the case: records, graph, vectors,
evidence files and audit log. In the app: Case settings, Exports, Build the package (the page states what the package holds and
leaves out); the package is kept 7 days and downloaded as a stream. Routes: `POST /api/cases/{id}/exports`,
`GET /api/cases/{id}/exports/{export_id}/download` (supports `Range`, so an interrupted download resumes). Before any hand-over
or import, run from `backend/`:

    python -m services.caseport verify <package>

It reads every part, checks every hash and count and says what is wrong (exit 1). The package's `.sha256` file beside it
adds the whole-file hash. Import into a new case, never over an existing one:

    python -m services.caseport import <package> --by <owner email> [--title "..."]

It verifies first, refuses a package from a newer schema, and writes an audit entry saying who imported what from where.
An operator's copy without the web application: `python -m services.caseport export <case id> <folder> --by <email>`.

**Missing: a customer's whole instance as one export.** With one Google Cloud project per customer, a whole-instance hand-over
is a recovery set (`bash deploy/backup-now.sh`) and the customer's evidence files, opened with `bash deploy/backup-crypt.sh open`.
No customer project exists yet, so this path has not been run.

## Offboarding

1. Export, as above, and have the customer confirm in writing that they hold what they need.
2. Hold a recovery set from that day: `bash deploy/backup-now.sh`. Its record is under `/mnt/owl-data/backups/manual/`.
3. Deactivate each of the customer's users: Admin, Users, deactivate (`PATCH /api/users/{id}` with `is_active: false`). They
   can no longer sign in; their names stay on what they did.
4. Delete each of the customer's cases under two-person deletion, below.
5. Note the day and run `bash deploy/backup-expiry.sh report --removed-on <that day>`. It gives the date the data is out of every
   set. Send that date to the customer, with the exception below.
6. On that date, run `bash deploy/backup-expiry.sh report` and confirm no set from before the removal is left.
7. For a customer with its own Google Cloud project: after step 6, delete the project. That removes the machine, its disks and
   its snapshots. Then destroy every copy of that customer's recovery key.

A case deletion removes the case's database rows, graph and vectors. The activity log keeps the case's title, its owner's id
and its record counts for good, as the record of the delete; these stay in every later set. The evidence files on disk are removed by each evidence
delete, not by the case delete.

**Missing: removal of a deleted case's evidence files in one action.** After the case delete, list what remains with
`ls /mnt/owl-data/evidence-data/<case id>` and remove it under two-person deletion. On a shared instance this is by hand.

## Backup expiry

Each dump script removes its own sets by age when it runs. No one acts for this to happen.

| Store | Kept | Set by |
|---|---|---|
| Postgres dumps | 30 days | `BACKUP_KEEP_DAYS` in `deploy/db-backup.sh` |
| Neo4j sets | 30 days | `BACKUP_KEEP_DAYS` in `deploy/backup-lib.sh` |
| Keys bundles | 30 days | `BACKUP_KEEP_DAYS` in `deploy/backup-lib.sh` |
| Chroma sets | 14 days | `BACKUP_KEEP_DAYS` in `deploy/chroma-backup.sh` |
| Boot disk snapshots | 14 days | Google Cloud schedule `default-schedule-1` |

- The newest set of a store is never removed, however old.
- A set holds every case on the instance. A case cannot be cut out of a set, so data removed from the app stays in sets
  taken before the removal until they age out. The activity log's record of the delete stays in later sets.
- `bash deploy/backup-expiry.sh report` lists sets, dates and retention for each store, and every file with no expiry.
- A hand-made dump in `/mnt/owl-data/backups` or `/mnt/owl-data/db-backups`, and a dump set aside as `.suspect` for being under
  half the size of the one before, has no expiry and is not sealed by a nightly run. The report lists each. It stays until it is
  deleted under two-person deletion. A customer's offboarding can cause a `.suspect` dump, so read the report after it.
- A set sealed to a key opens only with that key. Destroying every copy of the key makes every set sealed to it unreadable at
  once. On a shared instance that is every customer's backups, so it is used only for a whole instance.

**Missing: expiry in the evidence copy.** `deploy/evidence_copy.py` keeps a file removed at source, and each earlier version
under `superseded/`, for good. Until it has an expiry, a deleted file is removed from the copy by hand under two-person
deletion, after `python3 deploy/evidence_copy.py verify --dest <directory>` shows the copy whole.

## Two-person deletion

Two named people decide any deletion of a customer's case, and any deletion of a backup sooner than its retention.

For a backup:

```
bash deploy/two-person-delete.sh request neo4j-20261020-0210Z --by first@example.com --reason "customer request of 4 Nov"
bash deploy/two-person-delete.sh approve del-20261105-101500-1234 --by second@example.com
bash deploy/two-person-delete.sh execute del-20261105-101500-1234
```

For a case:

```
bash deploy/two-person-delete.sh request-case <case id> --by first@example.com --reason "offboarding"
bash deploy/two-person-delete.sh approve del-20261105-101500-1234 --by second@example.com
bash deploy/two-person-delete.sh execute del-20261105-101500-1234
```

Then the approver deletes the case in the app. The app's activity log records the delete.

- The asker cannot approve. A request lapses after 7 days.
- A backup is named, never given as a path. Only what the backup scripts write, suspect dumps and hand-made dumps can be named.
- The newest set of a store cannot be deleted.
- Every step is a line in `/mnt/owl-data/backups/deletions/log.tsv`, and `bash deploy/two-person-delete.sh list` shows each request.
- Before a case is deleted, confirm there is no legal hold on it. A case deletion cannot be undone from the app while Deleted
  items is switched off.

**Limits.** The names are typed by whoever is at the keyboard, so the book records two people's decision and root can still go
around it. **Missing: the app takes one person to delete a case.** A case owner's delete goes through at once. With one engineer
in the company the second person is someone outside engineering, and the first person runs the commands with them present.
