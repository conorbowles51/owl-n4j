"""The failed-files watch: board lines by plain reason, an alert when a case gains 10+ failed files in an hour or
the engine refuses a whole request, and none for failures the first run finds (lx-chunking, 8 Nov 2026)."""
import importlib.util
from pathlib import Path
from uuid import uuid4

spec = importlib.util.spec_from_file_location("watch", Path(__file__).parents[1] / "scripts" / "watch_failed_files.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

CASE = uuid4()
SIZE = "Client error '400 Bad Request' for url 'http://localhost:8003/cases/x/files'"


def rows(n, error=SIZE):
    return [(uuid4(), CASE, error) for _ in range(n)]


def test_the_first_run_writes_the_board_and_alerts_nothing_about_old_failures():
    board, alerts, state = watch.evaluate(rows(250) + rows(2, "Processing failed"), {str(CASE): "SB4"}, {}, 1000.0, [])
    assert alerts == []
    assert board[0].startswith("- **SB4**: 252 failed")
    assert "250 x The processing service refused the request this file was sent in" in board[0] and "2 x Processing stopped" in board[0]


def test_ten_new_failures_in_an_hour_alert_once_and_every_reason_is_named():
    old = rows(3)
    _, _, state = watch.evaluate(old, {}, {}, 1000.0, [])
    new = rows(10, "Unsupported image format/type")
    _, alerts, state = watch.evaluate(old + new, {str(CASE): "SB4"}, state, 1100.0, [])
    assert len(alerts) == 1 and "SB4: 10 files failed in the last hour" in alerts[0]
    assert "image format cannot be read" in alerts[0] and "refused the request" in alerts[0]
    _, again, _ = watch.evaluate(old + new, {str(CASE): "SB4"}, state, 1200.0, [])
    assert again == []


def test_nine_new_failures_do_not_alert():
    _, _, state = watch.evaluate([], {}, {}, 1000.0, [])
    _, alerts, _ = watch.evaluate(rows(9), {}, state, 1100.0, [])
    assert alerts == []


def test_a_whole_request_refused_by_the_engine_alerts():
    line = f"WARNING:app.refusals:request-refused POST /cases/{CASE}/files 400: Part exceeded maximum size of 1024KB."
    _, alerts, _ = watch.evaluate([], {str(CASE): "SB4"}, {"baseline_at": 1}, 1000.0, [line])
    assert len(alerts) == 1 and "refused 1 whole request" in alerts[0] and "1024KB" in alerts[0]
