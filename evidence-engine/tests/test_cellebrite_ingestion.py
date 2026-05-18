from app.models.job import JobStatus
from app.pipeline.cellebrite_ingestion import _progress_from_log


def test_cellebrite_log_steps_map_to_existing_job_statuses() -> None:
    assert _progress_from_log("Step 1/9: Detecting Cellebrite XML report...", 0.0) == (
        JobStatus.EXTRACTING_TEXT,
        0.02,
    )
    assert _progress_from_log("Step 8/9: Writing models to Neo4j...", 0.38) == (
        JobStatus.WRITING_GRAPH,
        0.45,
    )
    assert _progress_from_log("Step 9/9: Registering media files as evidence records...", 0.82) == (
        JobStatus.WRITING_GRAPH,
        0.90,
    )


def test_cellebrite_batch_logs_update_real_progress() -> None:
    assert _progress_from_log("Written 1000/2000 models (50.0%)", 0.45) == (
        JobStatus.WRITING_GRAPH,
        0.625,
    )
    assert _progress_from_log("Registered 250/500 media files", 0.90) == (
        JobStatus.WRITING_GRAPH,
        0.9400000000000001,
    )
