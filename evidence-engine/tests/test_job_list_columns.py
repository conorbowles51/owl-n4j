"""The case job list (polled by the backend's jobs panel) reads only the columns its answer uses."""
from sqlalchemy.dialects import postgresql

from app.api.routes.jobs import list_jobs_statement
from app.models.job import Job
from app.schemas.job import JobResponse


def _selected_columns() -> set[str]:
    compiled = list_jobs_statement("case-1").compile(dialect=postgresql.dialect())
    return {col[0] for col in compiled._result_columns}


def test_job_list_reads_every_answer_field_and_nothing_else() -> None:
    selected = _selected_columns()
    assert {Job.__table__.c[name].name for name in JobResponse.model_fields} == selected


def test_job_list_does_not_read_the_large_columns() -> None:
    selected = _selected_columns()
    for heavy in ("sibling_files", "folder_context", "effective_context", "effective_mandatory_instructions",
                  "effective_special_entity_types", "transcription", "transcription_segments", "merge_payload"):
        assert heavy not in selected


def test_job_list_keeps_the_case_filter_and_newest_first() -> None:
    sql = str(list_jobs_statement("case-1").compile(dialect=postgresql.dialect()))
    assert "WHERE jobs.case_id = " in sql
    assert sql.rstrip().endswith("ORDER BY jobs.created_at DESC")
