#!/usr/bin/env python3
"""Shell pixel diff between two style-shots folders (lx-style correction, Neil 2 Nov).

    python3 journeys/shell-diff.py <before-dir> <after-dir>

For each case view at 1440 in light and dark, compares the shell regions: the sidebar (x 0-223, full height),
the right rail (x 1392-1439) and the top strip of the main area (x 224-1391, y 0-55). Prints, per shot and region,
the share of pixels whose largest channel difference is over 8 (0.0 = identical), and the whole-image share.
Content below the top strip holds live data and is reported only as the whole-image figure.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

VIEWS = ["graph", "timeline", "map", "table", "financial", "cellebrite", "phones", "profiles", "dossiers",
         "evidence", "chat", "agent", "workspace", "reports", "settings"]
REGIONS = {"sidebar": (0, 0, 224, 900), "rail": (1392, 0, 1440, 900), "top": (224, 0, 1392, 56)}


def share(a, b):
    d = np.abs(a.astype(int) - b.astype(int)).max(axis=2)
    return float((d > 8).mean())


def main(before, after):
    rows = []
    for theme in ("light", "dark"):
        for v in VIEWS:
            name = f"{v}-{theme}-1440.png"
            pa, pb = Path(before) / name, Path(after) / name
            if not (pa.exists() and pb.exists()):
                rows.append({"shot": name, "missing": True})
                continue
            a = np.asarray(Image.open(pa).convert("RGB"))
            b = np.asarray(Image.open(pb).convert("RGB"))
            if a.shape != b.shape:
                rows.append({"shot": name, "size": [a.shape, b.shape]})
                continue
            row = {"shot": name}
            for r, (x0, y0, x1, y1) in REGIONS.items():
                row[r] = round(share(a[y0:y1, x0:x1], b[y0:y1, x0:x1]), 4)
            row["whole"] = round(share(a, b), 4)
            rows.append(row)
    for r in rows:
        print(json.dumps(r))
    ok = [r for r in rows if "sidebar" in r]
    for reg in list(REGIONS) + ["whole"]:
        vals = [r[reg] for r in ok]
        print(f"{reg}: mean {np.mean(vals):.4f} max {max(vals):.4f} over {len(vals)} shots")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
