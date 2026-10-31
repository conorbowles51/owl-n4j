# lx-measure WIP notes (branch lx/measure only; not for the release branch)

State 2026-10-31 02:48 UTC: all WS-H items (a-g) are live in 3745be94; recorder unit installed
(/etc/systemd/system/loupe-host-recorder.service, loupe.slice, CPUQuota 5%). Inbox clear. Status for readers:
headless/LX-MEASURE-STATUS.md. Log: headless/lx-measure-progress.md.

Remaining: acceptance "real-user page rows from >= 5 pages within 48 h" (beacons live from 01:13 31 Oct; no real
user has used the app since). Check at/after 2026-11-02 01:13 UTC:
  select page, count(*) from request_speed_pages
  where user_id is not null and user_id::text not like 'a2fd2e70%' group by page;
(read-only helper: /mnt/owl-data/tmp/lxm/q.py "<sql>"). Then quote it in STATUS and touch headless/lx-measure.DONE.

Scratch: /mnt/owl-data/tmp/lxm (gate.py + gate.jsonl, cached jobs token, private node_modules copy nm/ for vitest).
