"""Photo places stored as the phone's position get the media place kind, through services.phone.generic (followups
m111723091510458). Usage from backend/: python scripts/reclassify_media_places.py [--case <id>] [--apply]"""
import argparse
import json
import sys

sys.path.insert(0, ".")
from postgres.session import _get_engine  # noqa: E402
from services.phone import generic  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--case")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()
with _get_engine().begin() as c:
    if not a.apply:
        c.exec_driver_sql("SET TRANSACTION READ ONLY")
    print(json.dumps(generic.reclassify_media_places(c, a.case, apply=a.apply), indent=1, default=str))
