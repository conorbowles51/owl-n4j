"""Call one agent tool on a case, read-only, and print what the agent would get: status, summary, size, seconds
(lx-agentfit C and D: dry runs of the question tools on real data before they ship).

Every Postgres session of this process starts read-only (checked before anything runs). No chat model is called;
document search embeds its query with OpenAI as the live tool does. Output is case material: --out under
/mnt/owl-data/tmp, never the repo.

Usage (from backend/, via live-run.sh):
  financial_agent_fit_tool.py --case <id> --tool check_statements --args '{"statements": [...]}' [--out r.json]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

os.environ['PGOPTIONS'] = (os.environ.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on').strip()
_getaddrinfo = socket.getaddrinfo


def _guarded(host, *args, **kwargs):
    if host and any(name in str(host) for name in ('anthropic.com', 'googleapis.com', 'deepseek.com')):
        raise OSError('this script calls no chat model')
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _guarded
sys.path.insert(0, '.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--tool', required=True)
    ap.add_argument('--args', default='{}')
    ap.add_argument('--out')
    args = ap.parse_args()
    from sqlalchemy import text
    from postgres.session import _get_engine
    with _get_engine().connect() as c:
        if c.execute(text('SHOW default_transaction_read_only')).scalar() != 'on':
            raise SystemExit('refusing to run: sessions are not read-only')
    from services.agent.tools import AgentToolContext, make_agent_tools
    context = AgentToolContext(case_id=args.case)
    tools = {t.name: t for t in make_agent_tools(context)}
    started = time.perf_counter()
    out = tools[args.tool].invoke(json.loads(args.args))
    seconds = time.perf_counter() - started
    body = json.dumps(out, default=str, ensure_ascii=False)
    print(json.dumps(dict(status=out.get('status'), summary=out.get('summary'), chars=len(body),
                          seconds=round(seconds, 1)), ensure_ascii=False))
    if args.out:
        with open(args.out, 'w') as f:
            f.write(body)


if __name__ == '__main__':
    main()
