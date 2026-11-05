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
| Hash check of 300 evidence files | 151 seconds |
| The whole drill | 25 minutes |

## 1. Prepare

1. Install docker, nginx and the repo at `/home/conorbowles51/app-v3/owl-n4j`, at the commit named in the backup's
   `meta.env`.
2. Mount the data disk, or the disk or bucket holding the copy, at `/mnt/owl-data`.

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

## Switching on the evidence copy

1. Mount the disk or bucket, and mark it once: `python3 deploy/evidence_copy.py init --dest <directory>`. A run refuses
   an unmarked directory, so a mount that is missing after a reboot stops the copy and alerts.
2. Put `EVIDENCE_COPY_DEST=<directory>` in `/root/.config/loupe-backup/evidence-copy.env` (mode 600).
3. `cp deploy/owl-evidence-copy.* /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now owl-evidence-copy.timer`

The check and the drill then read the same file and include the copy.
