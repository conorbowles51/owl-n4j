"""The DeepSeek account balance, read with no model call (GET /user/balance costs no tokens). lx-agentfit R8/R10: a
measurement starts only when the balance covers its stated token budget, and the app shares the account.

Prints one JSON line: is_available, and per currency total, granted and topped-up balance. Exit 0 when the account
can serve requests, 2 when it cannot (empty), 1 when the balance could not be read.
Usage (from backend/, via live-run.sh): financial_deepseek_balance.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, '.')


def main() -> int:
    import httpx
    from services.agent.tools import _financial_session
    from services.ai_provider_credentials import get_provider_api_key
    with _financial_session() as s:
        key = get_provider_api_key(s, 'deepseek')
    if not key:
        print(json.dumps({'error': 'no DeepSeek key stored'}))
        return 1
    try:
        response = httpx.get('https://api.deepseek.com/user/balance', timeout=20,
                             headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
        response.raise_for_status()
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - reported, never retried
        print(json.dumps({'error': '%s: %s' % (type(exc).__name__, str(exc)[:200])}))
        return 1
    print(json.dumps(body))
    return 0 if body.get('is_available') else 2


if __name__ == '__main__':
    raise SystemExit(main())
