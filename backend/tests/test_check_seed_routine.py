"""The check-seed phone (docs/check-case-seed.md) forms a routine place by the production rules: its fixes, read back from
the report the builder writes, go through the same stay and place rules as a stored phone (cb-checkseed)."""
from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

from services.pattern_of_life import places, routine

BUILDER = Path(__file__).resolve().parents[2] / "evidence-engine" / "tests" / "phone" / "fixture_builder.py"


def builder():
    spec = importlib.util.spec_from_file_location("fixture_builder_seed", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses read the module of a class while it is defined
    spec.loader.exec_module(mod)
    return mod


def fixes(report: Path, ns: str):
    """(time, lat, lon, radius, phone, end) of each Location with an accuracy, as ``routine.presence`` returns them."""
    q = "{%s}" % ns
    out = []
    for model in ET.parse(report).getroot().iter(q + "model"):
        if model.get("type") != "Location":
            continue
        vals = {f.get("name"): (f.find(q + "value").text if f.find(q + "value") is not None else None)
                for f in model.iter(q + "field")}
        if not vals.get("GpsHorizontalAccuracy"):
            continue
        radius = places.radius_of(vals["GpsHorizontalAccuracy"], "gps_horizontal", "gps")[0]
        out.append((datetime.fromisoformat(vals["TimeStamp"]), float(vals["Latitude"]), float(vals["Longitude"]), radius, "x", None))
    return sorted(out, key=lambda r: r[0])


def test_the_check_seed_phone_has_one_routine_place(tmp_path):
    fb = builder()
    fb.build_case(fb.check_seed_case(), tmp_path)
    points = fixes(tmp_path / "C7" / "Report.xml", fb.NS)
    assert len(points) == 21 * 8
    assert all(p[3] <= routine.PARAMS["stay_max_radius_m"] for p in points)
    stays = routine.stays_of(points)
    assert len(stays) == 21
    labels = routine.dbscan(stays, routine.PARAMS["eps_m"], routine.PARAMS["min_samples"])
    assert Counter(labels) == {0: 21}
    assert len({s["start"].date() for s in stays}) >= routine.PARAMS["routine_min_days"]
