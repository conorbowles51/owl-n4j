# Server measurement plan: why statements are blocked (2 October 2026)

This is a plan for a Claude session running on the production server. Read all
of it before running anything.

## What this is for

Loupe imports bank statement PDFs into a forensic ledger. An investigator, Alex,
has had to work through many statements line by line. A code analysis on
2 October found five mechanisms that push work onto a person (listed under
"What the results decide" below), but it had no live numbers. The last real
production test ("Final Test", 27 to 28 September) ended with 233 statement
periods ready and 105 blocked, and nobody recorded **why** the 105 were blocked.

This session measures that. It produces counts only. It changes nothing.

Vocabulary used below:

- **Statement period**: one monthly (or cycle) statement inside a PDF. One PDF
  can hold many. Stored as a row in `financial_import_batch_items` when it went
  through a batch, or as a saved review in `evidence_files.metadata`.
- **Blocker**: a reason a period cannot be imported yet. Stored in the item's
  `summary` JSON: `summary->'problems'` (messages shown to the user) and, when
  admission ran, `summary->'admission'->'blockers'` (each with a `kind`).
- **Status** of a batch item: `ready`, `attention` (blocked), `imported`,
  `pending_import`, `skipped`, `assigned`, `duplicate_ignored`,
  `superseded_reading`, `removed`.

## Hard rules

1. **Read only.** No INSERT, UPDATE, DELETE, DDL, VACUUM or function that writes.
   Every psql session is opened read-only (see Setup). If a query errors with
   "read-only transaction", that is the guard working: stop and report it.
2. **Do not touch services.** No restart, stop, `docker compose up/down`, worker
   pause, reprocessing, retry, cache clear, deploy, `git pull`, or `git push`.
   Ingestion may be running for the team; it must not be interrupted.
3. **No case content leaves the database.** Never print or write names, account
   numbers, amounts, balances, descriptions, counterparties, file names or case
   titles. Report cases by the first 8 characters of their id. Normalise any
   message text with `regexp_replace(message, '[0-9]', '#', 'g')` and cut it to
   120 characters before grouping.
4. **Bounded cost.** Every query runs with a 60-second statement timeout. If a
   query times out, do not raise the limit; narrow it to one case and say so.
5. **Show Neil any query not in this file before running it.**
6. **Never print secrets.** Do not `cat` env files or print `POSTGRES_PASSWORD`.

## Setup

1. Find the database container without printing environment values:

   ```
   docker ps --format '{{.Names}}  {{.Image}}'
   ```

   Pick the Postgres container that backs Loupe. If more than one is plausible,
   ask Neil which one.

2. Read only the user and database name:

   ```
   docker exec <pg> printenv POSTGRES_USER
   docker exec <pg> printenv POSTGRES_DB
   ```

3. Define a read-only query helper for the session (zsh does not word-split a
   string, so use a function):

   ```
   q(){ docker exec -e PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=60000' <pg> psql -U <user> -d <db> -At -F' | ' -c "$1"; }
   ```

4. Prove the guard works before anything else. This must fail:

   ```
   q "create temporary table guard_check(x int)"
   ```

   Expected: `cannot execute CREATE TABLE in a read-only transaction`. If it
   succeeds, stop and tell Neil.

5. Confirm the expected tables exist:

   ```
   q "select table_name from information_schema.tables where table_schema='public' and table_name in ('financial_import_batches','financial_import_batch_items','evidence_files','financial_transactions','financial_source_documents','cases')"
   ```

Write results to `~/loupe-measurement-2026-10-02.md` on the server, **not** in
the repository. Counts and normalised messages only.

## Measurements

Run in order. Record each result under its number.

### M1. Size of the problem, by case

```
q "select left(b.case_id::text,8) as case_id, min(b.created_at)::date as first_batch, count(distinct b.id) as batches, count(i.id) as periods,
   count(*) filter (where i.status='ready') as ready,
   count(*) filter (where i.status='attention') as blocked,
   count(*) filter (where i.status='imported') as imported,
   count(*) filter (where i.status='duplicate_ignored') as dup_ignored,
   count(*) filter (where i.status='skipped') as skipped
   from financial_import_batches b join financial_import_batch_items i on i.batch_id=b.id
   group by 1 order by periods desc"
```

Then ask Neil which case ids are Final Test and which are Alex's real work. He
can map ids to titles himself; do not print titles.

### M2. Blocked periods by bank

```
q "select coalesce(nullif(i.summary->>'institution',''),'(unknown)') as bank, i.status, count(*)
   from financial_import_batch_items i group by 1,2 order by 1,3 desc"
```

### M3. Blocker kinds on currently blocked periods (admission ran)

```
q "select coalesce(nullif(i.summary->>'institution',''),'(unknown)') as bank,
   b->>'kind' as kind, coalesce(b->>'field', b->>'check', '') as detail,
   count(*) as blockers, count(distinct i.id) as periods
   from financial_import_batch_items i, jsonb_array_elements(coalesce(i.summary->'admission'->'blockers','[]'::jsonb)) b
   where i.status='attention' group by 1,2,3 order by 1,4 desc"
```

### M4. Blocker messages where admission did not run

Admission only runs once basic validation passes, so some blocked periods have
messages but no `admission` block.

```
q "select left(regexp_replace(p->>'message','[0-9]','#','g'),120) as message, count(*) as rows, count(distinct i.id) as periods
   from financial_import_batch_items i, jsonb_array_elements(coalesce(i.summary->'problems','[]'::jsonb)) p
   where i.status='attention' and i.summary->'admission' is null
   group by 1 order by 2 desc limit 40"
```

### M5. How many problems block each period

This tests the claim that one doubtful row stops a whole statement.

```
q "select case when (summary->>'problem_count')::int = 0 then '0'
                when (summary->>'problem_count')::int = 1 then '1'
                when (summary->>'problem_count')::int <= 5 then '2-5'
                when (summary->>'problem_count')::int <= 20 then '6-20'
                else '21+' end as problems,
   count(*) as periods, sum((summary->>'transaction_count')::int) as rows_held
   from financial_import_batch_items where status='attention' group by 1 order by 1"
```

### M6. Periods blocked only by doubtful rows while the balances match

These are the periods the "confirm from printed balances" and "import with a
flag" rules would release. This is the most important number.

```
q "with blocked as (
     select i.id, i.summary->>'institution' as bank, i.summary->>'balance_status' as balance,
            coalesce(i.summary->'admission'->'blockers','[]'::jsonb) as blockers
     from financial_import_batch_items i where i.status='attention' and i.summary->'admission' is not null)
   select coalesce(nullif(bank,''),'(unknown)') as bank, balance,
     count(*) filter (where not exists (select 1 from jsonb_array_elements(blockers) b where b->>'kind' <> 'reading')) as only_reading,
     count(*) as all_blocked
   from blocked group by 1,2 order by 1,2"
```

### M7. Balance differences by check type

Sizes the dropped-row work. A running-balance or closing difference on a layout
with per-row balances usually means a missing or misread row.

```
q "select coalesce(nullif(i.summary->>'institution',''),'(unknown)') as bank, b->>'check' as check_kind, count(distinct i.id) as periods
   from financial_import_batch_items i, jsonb_array_elements(coalesce(i.summary->'admission'->'blockers','[]'::jsonb)) b
   where i.status='attention' and b->>'kind'='arithmetic' group by 1,2 order by 1,3 desc"
```

### M8. Is the row-by-row balance check running?

Inspect the shape of one check entry first (keys only, no values):

```
q "select distinct jsonb_object_keys(c) from financial_import_batch_items i, jsonb_array_elements(coalesce(i.summary->'checks','[]'::jsonb)) c limit 30"
```

Then count, per bank and status, how often the `running_balance` check is
missing or unavailable. Checked against a local copy on 2 October: each check
has `kind` and `status`, with status values such as `matches` and
`unavailable`. If the shape query shows different keys, show Neil the adjusted
query first:

```
q "select coalesce(nullif(i.summary->>'institution',''),'(unknown)') as bank, i.status,
   count(*) filter (where c is null) as no_running_check,
   count(*) filter (where c->>'status' = 'unavailable') as running_unavailable,
   count(*) as periods
   from financial_import_batch_items i
   left join lateral (select x from jsonb_array_elements(coalesce(i.summary->'checks','[]'::jsonb)) x where x->>'kind'='running_balance' limit 1) r(c) on true
   group by 1,2 order by 1,2"
```

`imported` periods with the running check unavailable were reconciled on
opening and closing balances only. Report that number separately: it is ledger
exposure, not workload.

### M9. Duplicates

```
q "select status, count(*) from financial_import_batch_items where status in ('duplicate_ignored') group by 1"
q "select count(*) from financial_import_batch_items i, jsonb_array_elements(coalesce(i.summary->'problems','[]'::jsonb)) p
   where i.status='attention' and p->>'message' ilike '%duplicate%'"
```

### M10. Manual effort already spent, from saved reviews

Saved reviews live in `evidence_files.metadata->'financial_review_progress'`,
keyed by statement period. Each has `request->'rows'`; rows a person touched
usually carry a non-empty `reason` or `excluded=true`. Earlier versions are in
`metadata->'financial_review_history'`.

```
q "select left(f.case_id::text,8) as case_id, count(*) as saved_periods,
   sum((select count(*) from jsonb_array_elements(coalesce(v->'request'->'rows','[]'::jsonb)) r where coalesce(r->>'reason','') <> '')) as rows_with_reason,
   sum((select count(*) from jsonb_array_elements(coalesce(v->'request'->'rows','[]'::jsonb)) r where (r->>'excluded')::boolean)) as rows_excluded,
   sum(jsonb_array_length(coalesce(f.metadata->'financial_review_history','[]'::jsonb))) as earlier_versions
   from evidence_files f, jsonb_each(f.metadata->'financial_review_progress') e(k,v)
   group by 1 order by 2 desc"
```

### M11. Same dates stamped across several periods

Tests whether the group date fix has put one date on several months.

```
q "select left(file_id::text,8) as file, summary->>'period_start' as start_shape, count(*) as periods
   from financial_import_batch_items
   where coalesce(summary->>'period_end','') <> '' and status <> 'removed'
   group by file_id, summary->>'period_start', summary->>'period_end', summary->>'account'
   having count(*) > 1 order by 3 desc limit 20"
```

Print the count of groups and the largest group size only. The dates themselves
are case content; replace `start_shape` with `''` if it shows real dates.

### M12. Request failures ("Failed to fetch")

Count, do not copy, recent error responses from the backend or proxy logs. Find
the right containers with `docker ps`, then for each:

```
docker logs --since 336h <container> 2>&1 | grep -cE ' (500|502|503|504) '
docker logs --since 336h <container> 2>&1 | grep -E ' (500|502|503|504) ' | grep -oE '(GET|POST|PUT|PATCH|DELETE) /api/[a-z_/-]+' | sed -E 's#/[0-9a-f-]{36}#/{id}#g' | sort | uniq -c | sort -rn | head -15
```

If the log format does not match these patterns, show Neil one redacted line
format (method, path with ids replaced, status) before writing a new pattern.

## What the results decide

Map each result to the plan from the 2 October analysis:

| Result | Plan step it sizes |
|---|---|
| M6 `only_reading` with balances matching | Step 2 (confirm rows from printed balances) and step 5 (import flagged). If this is large, step 2 comes first. |
| M7 running or closing differences on Andrews or BBVA | Step 3 (find dropped rows from the balance gap and reread only that strip). |
| M3 `no_activity`, missing start date, Merrick | Step 4 (record bank-wide facts once; group confirmations). |
| M8 imported periods with running check unavailable | Defect: one bad date silently disables the running check. Fix in step 1; the count says how many imported statements to recheck. |
| M10 rows with reason or excluded | The manual effort already spent, as a baseline. |
| M11 repeated date groups | Defect: one date applied to several months. If any exist, list the affected case ids for Neil to review. |
| M12 error counts by endpoint | Starting evidence for the unexplained request failures. |

## Report back

Finish with a short summary for Neil, in plain language, with no internal
vocabulary undefined:

1. Per case (by id prefix): periods, ready, blocked, imported.
2. The top five reasons periods are blocked, with counts of periods, by bank.
3. The M6 number, stated as: "N blocked periods would be released by
   confirming rows from printed balances, out of M blocked."
4. Ledger exposure from M8 and M11, if any.
5. Anything that could not be measured and why.

Then stop. Do not start fixing anything on the server. The code changes are
made in the repository and released through the normal path.
