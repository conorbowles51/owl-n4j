from app.models.job import JobStatus
from app.pipeline.cellebrite.models import CellebriteReport, ParsedModel
from app.pipeline.cellebrite.neo4j_writer import CellebriteNeo4jWriter
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


def test_cellebrite_writer_adds_canonical_time_from_timestamp_only_nodes() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.calls = []

        def run_query(self, query, **params):
            self.calls.append({"query": query, "params": params})

    db = FakeDb()
    writer = CellebriteNeo4jWriter(
        db,
        case_id="case-1",
        report_key="report-1",
        report=CellebriteReport(),
    )
    model = ParsedModel(
        model_type="VisitedPage",
        model_id="abcdef1234567890",
        fields={
            "Url": "https://example.test",
            "TimeStamp": "2025-04-12T06:21:47-04:00",
        },
    )

    writer._write_visited_page(model)

    props = db.calls[0]["params"]["props"]
    assert props["date"] == "2025-04-12"
    assert props["time"] == "06:21"
    assert props["timestamp"] == "2025-04-12T06:21:47-04:00"
    assert "end_time" not in props
