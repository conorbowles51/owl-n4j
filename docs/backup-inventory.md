# Backup inventory

Every store Loupe needs to come back, where it lives and what protects it. Sizes are measured on 5 November 2026.
There are two disks: the boot disk `investigation-platform` (500 GB SSD) and the data disk `owl-data` (1 TB standard).
The boot disk has a daily snapshot (`default-schedule-1`, 06:20 UTC, kept 14 days). The data disk has no snapshot.

| Store | Where | Size | Disk | Protection | Off its disk? |
|---|---|---|---|---|---|
| Postgres `owl_db` | `postgres/data`, container `owl-v2-pg` | 13 GB on disk, 1.28 GB dump | boot | Daily dump 01:30 UTC to `/mnt/owl-data/backups/scheduled`, 30 days, with row counts per table and case. Disk snapshot. | Yes, dump on the data disk |
| Neo4j | `neo4j/data`, container `owl-v2-n4j` | 2.3 GB on disk, 139 MB dump | boot | Daily dump 02:10 UTC with no stop of the live database, to `/mnt/owl-data/backups/neo4j`, 30 days, with counts per case. Disk snapshot. | Yes, dump on the data disk |
| Chroma vectors | docker volume `owl-v2_chromadb-data` | 1.44 GB | boot | Daily copy 02:30 UTC to `/mnt/owl-data/backups/chroma`, 14 days, with counts per collection. Disk snapshot. | Yes, copy on the data disk |
| Evidence originals and derived files | `/mnt/owl-data/evidence-data`, mounted at `evidence-data` | 68 GB, 365,098 files | data | Copy tool built; off until a second location is named | **No** |
| Evidence engine working files | `/mnt/owl-data/evidence-files`, mounted into the volume `owl-v2_evidence-files` | 19 GB | data | Copy tool built; off until a second location is named | **No** |
| Older evidence paths | `ingestion/data` | 2.3 GB, 5,585 `evidence_files` rows | boot | Disk snapshot; in the copy tool's sources | Yes, snapshot only |
| Former evidence volume | `/var/lib/docker/volumes/owl-v2_evidence-files/_data.ssd-old` | 14 GB | boot | Disk snapshot. No live row points at it; it holds byte-identical copies of files the live paths also hold. Not in the copy tool's sources. | Yes, snapshot |
| Previous platform's data | `/mnt/owl-data/ingestion-data`, bound to `app_v2/ingestion/data` | 205 GB | data | In the copy tool's sources; off until a second location is named | **No** |
| Reference data | `/mnt/owl-data/reference-data` | 47 MB | data | In the copy tool's sources | **No** |
| Database and vector backups | `/mnt/owl-data/backups` | 5.0 GB, about 45 GB at full retention (estimate, not measured) | data | In the copy tool's sources | **No** |
| Keys and env | `.env`, deploy key, nginx sites, systemd units, `/etc/fstab`, docker daemon config | 50 files | boot | Daily encrypted bundle 02:05 UTC to `/mnt/owl-data/backups/keys`, 30 days | Yes, encrypted on the data disk |
| Uploads in flight | `/mnt/owl-data/uploads-tus` | 4.6 KB, 2 files | data | None. A partial upload is resumed or sent again by the person uploading. Finished uploads are in the evidence stores. | Not needed |
| Redis | anonymous docker volume, `owl-v2-redis` | 12 keys, no append-only file | boot | Disk snapshot. Holds the job queues only; the work is recorded in Postgres. | Not needed |
| Map tiles | `/mnt/owl-data/loupe-basemap` | 130 GB, 797 files | data | None. Public data, rebuilt by `deploy/refresh-basemap.sh`. | Not needed |
| Frontend build | `loupe-frontend/current` | 22 MB | boot | Rebuilt from git by the release | Not needed |
| Code | GitHub `conorbowles51/owl-n4j` | | | Off the box | Yes |

## What a backup set holds

Each set records the application commit and the image it came from (`meta.env`, or `.meta` beside a Postgres dump), and
the schema version travels inside the dump (`alembic_version`). `docs/backup-restore.md` holds the restore steps.

## Evidence copy: what it needs

The sources above total about 300 GB (68 + 19 + 2.3 + 205 + 0.05 + 5). The boot disk has 42 GB free, so it cannot hold
the copy. The destination is a mounted directory, a disk or a bucket, of at least 350 GB (estimate, not measured,
allowing for growth). `/mnt/owl-data/fin-real` (132 GB) and `/mnt/owl-data/fin-wt` hold working files of the job fleet,
not stores of the application, and are not in the copy.

`/mnt/owl-data/ingestion-data` has no row in the live database pointing at it and the older service is stopped. It stays
in the copy because no check shows its files exist anywhere else. Removing its `--source` line drops 205 GB.

## Health

`deploy/backup-check.sh` runs hourly and writes `/mnt/owl-data/backups/status.tsv`. The status board shows it under
Backups. A failed or stale backup of any store alerts the coordinator inbox through `headless/db-backup-alert.sh`, once
per reason per 12 hours.
