-- Rows per table and per case: "table <tab> case id <tab> rows". Tables without a case_id column give one line with
-- an empty case id. Read by deploy/db-backup.sh in the snapshot the dump reads, and by deploy/restore-drill.sh on the
-- restored database and on live. Run with psql -At -F '<tab>'.
SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'case_id' AND NOT a.attisdropped)
            THEN format('SELECT %L, case_id::text, count(*) FROM %I GROUP BY 2', c.relname, c.relname)
            ELSE format('SELECT %L, '''', count(*) FROM %I', c.relname, c.relname) END
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname
\gexec
