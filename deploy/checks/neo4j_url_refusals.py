#!/usr/bin/env python3
"""Neo4j refuses every query that would fetch a URL or read a server file (lx-neo4jconf).

A READ query can carry LOAD CSV, which makes the database server fetch any address it can reach (its own HTTP port,
the host, the cloud metadata service) or read files under its import directory. The app never uses LOAD CSV or
apoc.load, and the query console refuses them by text, but a text check can be got past by building the query as a
string inside apoc.cypher.run. The server itself has to refuse. docker-compose.yml sets that up:

  internal.dbms.cypher_ip_blocklist                  every address (0.0.0.0/0, ::/0), private ranges listed too
  dbms.security.allow_csv_import_from_file_urls      false

Each probe below runs in a READ session, as the console does, and passes only when Neo4j refuses it with the error
that names one of those settings. A connection error or any other failure is reported as a failure, never a pass.

    python deploy/checks/neo4j_url_refusals.py [--uri bolt://localhost:7688] [--user neo4j]
    (password from NEO4J_PASSWORD, else .env or backend/.env)

Exit 0: every probe refused. Exit 1: at least one probe was not refused. Exit 2: could not run.
No probe reaches the internet: the public-address probe uses 203.0.113.1 (TEST-NET-3, never routed).
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (name, query). Every query is a read; none writes.
PROBES = (
    ('LOAD CSV from the server itself (http://127.0.0.1)',
     "LOAD CSV FROM 'http://127.0.0.1:7474/' AS row RETURN count(row) AS n"),
    ('LOAD CSV from a host name that resolves to the server (http://localhost)',
     "LOAD CSV FROM 'http://localhost:7474/' AS row RETURN count(row) AS n"),
    ('LOAD CSV from the cloud metadata address (http://169.254.169.254)',
     "LOAD CSV FROM 'http://169.254.169.254/computeMetadata/v1/' AS row RETURN count(row) AS n"),
    ('LOAD CSV from IPv6 loopback (http://[::1])',
     "LOAD CSV FROM 'http://[::1]:7474/' AS row RETURN count(row) AS n"),
    ('LOAD CSV from a public address (http://203.0.113.1)',
     "LOAD CSV FROM 'http://203.0.113.1/x.csv' AS row RETURN count(row) AS n"),
    ('LOAD CSV from a file (file:///)',
     "LOAD CSV FROM 'file:///probe.csv' AS row RETURN count(row) AS n"),
    ('apoc.cypher.run wrapping a LOAD CSV built from strings',
     "CALL apoc.cypher.run('LOAD ' + 'CSV FROM ' + $u + ' AS row RETURN count(row) AS n', {}) YIELD value "
     "RETURN value.n AS n"),
    ('apoc.cypher.run wrapping a file LOAD CSV built from strings',
     "CALL apoc.cypher.run('LOAD ' + 'CSV FROM ' + $f + ' AS row RETURN count(row) AS n', {}) YIELD value "
     "RETURN value.n AS n"),
    ('apoc.load.json from the server itself',
     "CALL apoc.load.json('http://127.0.0.1:7474/') YIELD value RETURN count(value) AS n"),
)
PARAMS = {'u': "'http://127.0.0.1:7474/'", 'f': "'file:///probe.csv'"}

# The refusal Neo4j gives for each setting (5.26). Anything else (a timeout, a missing file, a connection refused)
# means the server tried, so it is not a refusal.
REFUSED = re.compile(
    r'blocked via the configuration property internal\.dbms\.cypher_ip_blocklist'
    r'|configuration property [\'"]?dbms\.security\.allow_csv_import_from_file_urls[\'"]? is false'
    r'|apoc\.import\.file\.enabled|Import from files not enabled'
    r'|is unavailable because it is sandboxed',
    re.IGNORECASE,
)


def _password():
    if os.environ.get('NEO4J_PASSWORD'):
        return os.environ['NEO4J_PASSWORD']
    for env in (ROOT / '.env', ROOT / 'backend' / '.env'):  # the live service reads the repo-root .env
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith('NEO4J_PASSWORD='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    return None


def run(uri, user, password):
    """[(probe name, refused?, detail)] for every probe."""
    from neo4j import GraphDatabase, READ_ACCESS

    results = []
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        for name, query in PROBES:
            try:
                with driver.session(default_access_mode=READ_ACCESS) as session:
                    rows = session.run(query, PARAMS).data()
                results.append((name, False, f'ran and returned {rows!r}'))
            except Exception as exc:  # noqa: BLE001 - classified by message below
                message = ' '.join(str(getattr(exc, 'message', None) or exc).split())
                results.append((name, bool(REFUSED.search(message)), message[:300]))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--uri', default=os.environ.get('NEO4J_URI', 'bolt://localhost:7688'))
    parser.add_argument('--user', default=os.environ.get('NEO4J_USER', 'neo4j'))
    args = parser.parse_args(argv)
    password = _password()
    if not password:
        print('NOT RUN: no Neo4j password (NEO4J_PASSWORD, .env or backend/.env)')
        return 2
    try:
        results = run(args.uri, args.user, password)
    except Exception as exc:  # noqa: BLE001
        print(f'NOT RUN: could not reach Neo4j at {args.uri}: {exc}')
        return 2
    for name, refused, detail in results:
        print(f"{'REFUSED ' if refused else 'NOT REFUSED'}  {name}: {detail}")
    failed = sum(1 for _, refused, _ in results if not refused)
    print(f'{len(results) - failed} of {len(results)} probes refused')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
