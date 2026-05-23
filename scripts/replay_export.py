#!/usr/bin/env python3
"""
Stream an APOC-style Cypher export file into Neo4j, statement-by-statement.

Why this exists: cypher-shell -f and apoc.cypher.runFile both choked on
the 197MB export script (heap OOM in cypher-shell; runFile not bundled in
this APOC). The python driver doesn't have those limits — it streams the
file, parses one statement per semicolon-terminated line, and submits it.
"""

from __future__ import annotations

import os
import sys
import time
from neo4j import GraphDatabase

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")

if len(sys.argv) < 2:
    print(f"usage: {sys.argv[0]} <path-to-export.cypher>", file=sys.stderr)
    sys.exit(2)

path = sys.argv[1]

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
total = 0
errors = 0
t0 = time.monotonic()
last_report = t0

try:
    with driver.session(database="neo4j") as session:
        with open(path, "r") as f:
            buf: list[str] = []
            for line in f:
                buf.append(line)
                stripped = line.rstrip()
                # APOC export emits one statement per line terminated by ';'
                if stripped.endswith(";"):
                    stmt = "".join(buf).rstrip()
                    # Strip trailing semicolon — neo4j driver doesn't want it.
                    if stmt.endswith(";"):
                        stmt = stmt[:-1]
                    buf = []
                    if not stmt:
                        continue
                    try:
                        session.run(stmt).consume()
                        total += 1
                    except Exception as exc:
                        errors += 1
                        # Surface the first 3 errors verbatim, then count silently.
                        if errors <= 3:
                            print(
                                f"\n[err {errors}] statement #{total + errors} "
                                f"failed: {exc}\n  snippet: {stmt[:200]}...",
                                file=sys.stderr,
                                flush=True,
                            )

                    now = time.monotonic()
                    if now - last_report >= 10.0:
                        last_report = now
                        print(
                            f"  {total} stmt OK / {errors} err "
                            f"in {now - t0:.1f}s "
                            f"({total / max(now - t0, 1e-9):.1f}/s)",
                            flush=True,
                        )
finally:
    driver.close()

elapsed = time.monotonic() - t0
print(
    f"\nDone: {total} statements applied, {errors} errors, {elapsed:.1f}s "
    f"({total / max(elapsed, 1e-9):.1f}/s)"
)
sys.exit(0 if errors == 0 else 1)
