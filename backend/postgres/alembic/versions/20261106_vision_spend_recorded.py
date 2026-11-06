"""Statement page-image readings paid for before they wrote cost records.

Their cost was kept only on the stored reading, so a case's AI spend left it out. One cost record per stored reading
with a cost, at the reading's own time and price: 212 file readings, $15.13, and 58 description readings, $1.56, on
5 Nov. Where a statement was read again only the latest reading is stored, so this is what is known, not every dollar
ever spent. Runs once; the new records are marked, and downgrade removes exactly those.
"""
from alembic import op

revision = "20261106_vision_spend_recorded"
down_revision = "20261105_pending_chunk_vectors"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO cost_records (id, job_type, case_id, provider, model_id, cost_usd, operation_kind, evidence_file_id,
                                  pricing_version, description, extra_metadata, created_at, updated_at)
        SELECT gen_random_uuid(), 'ingestion', c.id,
               COALESCE(NULLIF(reading.value->>'provider', ''),
                        CASE WHEN reading.value->>'model' LIKE 'deepseek%' THEN 'deepseek' ELSE 'openai' END),
               reading.value->>'model', (reading.value->>'cost_usd')::numeric, 'vision', f.id, 'vision-reader-v1',
               'Statement page-image reading (recorded from the stored reading)',
               jsonb_build_object('workload', 'financial_vision', 'recorded_from', 'stored_reading',
                                  'reading_key', reading.key),
               (reading.value->>'at')::timestamptz, (reading.value->>'at')::timestamptz
        FROM evidence_files f
        JOIN cases c ON c.id = f.case_id
        CROSS JOIN LATERAL jsonb_each(f.metadata->'financial_vision_reading') AS reading
        WHERE f.metadata ? 'financial_vision_reading'
          AND reading.value ? 'cost_usd' AND (reading.value->>'cost_usd') IS NOT NULL
          AND reading.value ? 'model' AND reading.value ? 'at'
    """)
    op.execute("""
        INSERT INTO cost_records (id, job_type, case_id, provider, model_id, cost_usd, operation_kind, evidence_file_id,
                                  pricing_version, description, extra_metadata, created_at, updated_at)
        SELECT gen_random_uuid(), 'ingestion', c.id,
               COALESCE(NULLIF(lines->>'provider', ''),
                        CASE WHEN lines->>'model' LIKE 'deepseek%' THEN 'deepseek' ELSE 'openai' END),
               lines->>'model', (lines->>'cost_usd')::numeric, 'vision', d.evidence_file_id, 'vision-reader-v1',
               'Statement description reading (recorded from the stored reading)',
               jsonb_build_object('workload', 'financial_vision', 'recorded_from', 'stored_reading'),
               (lines->>'at')::timestamptz, (lines->>'at')::timestamptz
        FROM financial_source_documents d
        JOIN cases c ON c.id = d.case_id
        CROSS JOIN LATERAL (SELECT d.metadata->'vision_description_lines' AS lines) AS stored
        WHERE d.metadata ? 'vision_description_lines' AND (lines->>'cost_usd') IS NOT NULL
          AND lines ? 'model' AND lines ? 'at'
    """)


def downgrade():
    op.execute("DELETE FROM cost_records WHERE extra_metadata->>'recorded_from' = 'stored_reading'")
