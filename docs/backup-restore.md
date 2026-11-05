# Restoring Loupe from backup

For a person restoring onto a new machine, or replacing one store. Run as root. The weekly drill
(`deploy/restore-drill.sh`) runs the database, graph, vector and evidence-hash steps below; its report is in
`/mnt/owl-data/backups/drills/`, each ending `RESULT PASS` or `RESULT FAIL`.

Times come from the drill on the live box under load (load average 35-45), with the scratch containers held to 2 CPUs
and 2 GB of memory. A machine with nothing else running is faster.

| Step | Drill time |
|---|---|
| Postgres restore | 16 minutes |
| Neo4j load and start | under 4 minutes |
| Neo4j consistency check | 73 seconds |
| Chroma unpack and start | 84 seconds |
| Every evidence row checked against the disk, and a hash check of 300 files | 3 minutes |
| The whole drill | 25 minutes |

## 1. Prepare

1. Install docker, nginx and the repo at `/home/conorbowles51/app-v3/owl-n4j`, at the commit named in the backup's
   `meta.env`.
2. Mount the data disk, or the disk or bucket holding the copy, at `/mnt/owl-data`.

## Sealed files

A file ending `.gpg` is a sealed dump. It opens with the recovery key, kept in the password manager and never on the
machine. Save the key to a file in memory, and open each file before the step that needs it:

```
sha256sum -c owl_db-YYYYMMDD-HHMMZ.dump.gpg.sha256     # proves the file, with no key
bash deploy/backup-crypt.sh open owl_db-YYYYMMDD-HHMMZ.dump.gpg /dev/shm/recovery.asc > owl_db-YYYYMMDD-HHMMZ.dump
```

The sealed files are `owl_db-*.dump.gpg`, and `neo4j.dump.gpg`, `system.dump.gpg`, `hnsw.tar.gpg`, `chroma.sqlite3.gpg` in
their sets. Delete `/dev/shm/recovery.asc` and the opened files when finished. The keys bundle is not sealed to this key: it
has its own passphrase, step 2.

`bash deploy/backup-crypt.sh status` shows the state on this machine. With no recovery key, dumps are plain. With a key
whose custody is not proven, each dump is there both plain and sealed. With custody proven, a nightly run leaves only the sealed file. A hand-made dump is not touched by a nightly run: `status` counts
them, and `bash deploy/backup-crypt.sh seal-file <file>` seals one.

## 2. Keys and settings

The bundle is encrypted. The passphrase is in `/root/.config/loupe-backup/passphrase` and in Neil's password manager.
On a new machine, put it in that file (mode 600) first.

```
mkdir /root/opened
bash deploy/keys-bundle.sh open keys-YYYYMMDD-HHMMZ /root/opened
```

Every file comes back under `/root/opened` at its original path: `.env`, deploy key, nginx sites, systemd units,
`/etc/fstab`, docker daemon config. Copy each to its place. `files.tsv` beside the bundle lists names, sizes and hashes.
Delete `/root/opened` when finished.

## 3. Postgres

```
docker compose up -d postgres            # empty database, from the restored .env
docker exec -i owl-v2-pg pg_restore -U owl_us -d owl_db --no-owner --no-privileges \
    < /mnt/owl-data/backups/scheduled/owl_db-YYYYMMDD-HHMMZ.dump
```

Check it: run `deploy/pg-counts.sql` through `psql -AtqX -F $'\t'`, sort it with `LC_ALL=C sort`, and compare it with
`owl_db-YYYYMMDD-HHMMZ.counts.tsv`. The two are identical.

## 4. Neo4j

With the live container stopped, and `S` as the set directory under `/mnt/owl-data/backups/neo4j`:

```
for db in neo4j system; do
  docker run --rm -v "$PWD/neo4j/data:/data" -v "$S:/in:ro" neo4j:5 \
      neo4j-admin database load "$db" --from-path=/in --overwrite-destination=true
done
chown -R 7474:7474 neo4j/data
docker compose up -d neo4j
```

Check it: nodes and relationships per case equal `counts.tsv` in the set. The query is `COUNTS_QUERY` in
`deploy/neo4j-backup.sh`. Use the image named in `meta.env` if `neo4j:5` has moved on.

## 5. Chroma

With the container stopped, and `S` as the set directory under `/mnt/owl-data/backups/chroma`:

```
V=/var/lib/docker/volumes/owl-v2_chromadb-data/_data
tar -C "$V" -xf "$S/hnsw.tar"
cp "$S/chroma.sqlite3" "$V/"
docker compose up -d chromadb
```

Chroma brings each index forward from its own queue on start. Check it: records per collection equal `counts.tsv`.
The search setting comes back with the copy; `backend/scripts/chroma_reach.py settings --url http://127.0.0.1:8101` shows it.
Then check that every stored record can be found: `python3 -I backend/scripts/chroma_reach.py check --url http://127.0.0.1:8101 --out reach.json`.
The drill runs this every week and alerts on any record it misses. To repair records nothing links to, put their ids in
`/mnt/owl-data/backups/chroma-relink/<collection>.ids` (mode 600, one id per line, those with `any_depth` false in
`reach.json`): the next backend release re-adds them from their stored copy during its pause.

## 6. Evidence files

The copy holds each store under `files/<label>/` with the same relative paths: `evidence-data`, `evidence-files`,
`ingestion` (`ingestion/data` in the checkout), `ingestion-data`, `reference-data`, `backups`.

```
cd <copy location> && sha256sum -c --quiet MANIFEST.sha256     # proves every file; no output means all match
rsync -a --numeric-ids files/evidence-data/ /mnt/owl-data/evidence-data/
rsync -a --numeric-ids files/evidence-files/ /mnt/owl-data/evidence-files/
rsync -a --numeric-ids files/ingestion/ /home/conorbowles51/app-v3/owl-n4j/ingestion/data/
rsync -a --numeric-ids files/reference-data/ /mnt/owl-data/reference-data/
```

The copy is written mode 600: `chown -R conorbowles51:conorbowles51` the restored trees. A file that changed at source
has its earlier copy under `superseded/`.

## 7. Bring it up and check

1. `systemctl daemon-reload`, then enable the units restored in step 2.
2. Start the app through a normal release. Map tiles rebuild with `deploy/refresh-basemap.sh`.
3. Sign in, open a case, open a statement and a citation, run a search.
4. Compare `evidence_files.sha256` with a sample of files on disk, as `drill_evidence` in `deploy/restore-drill.sh` does.

## Switching on encryption

`bash deploy/backup-crypt.sh new-key` at a terminal, as root. It shows the private key once, and asks for it to be pasted back
from the password manager, which proves the saved copy opens this machine's backups. Only then does a nightly run remove a
plain dump. It offers a second key for the weekly drill. That key stays on the boot disk, is used only by the drill, and is
what lets the drill open sealed sets; without it the drill reports a failure once sets are sealed-only.

## A set before a release

`bash deploy/backup-now.sh --check` says whether a set can run now. `bash deploy/backup-now.sh` takes one: keys, Postgres, Neo4j
and Chroma, through the nightly scripts, in the same directories, under the same retention. It refuses at once when memory or
disk is short, and writes its record to `/mnt/owl-data/backups/manual/`.

## Switching on the evidence copy

Prove the recovery key first, and seal any hand-made dumps. Until the key is proven, plain dumps are copied too, because a copy
no one can open is no copy; a copied plain dump stays in the copy. Once it is proven, a dump with a sealed file beside it goes
only sealed.

1. Mount the disk or bucket, and mark it once: `python3 deploy/evidence_copy.py init --dest <directory>`. A run refuses
   an unmarked directory, so a mount that is missing after a reboot stops the copy and alerts.
2. Put `EVIDENCE_COPY_DEST=<directory>` in `/root/.config/loupe-backup/evidence-copy.env` (mode 600).
3. `cp deploy/owl-evidence-copy.* /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now owl-evidence-copy.timer`

The check and the drill then read the same file and include the copy.
