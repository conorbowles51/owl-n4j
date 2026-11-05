"""A small ASGI app for the supervisor's tests: real uvicorn workers, no Loupe. Its behaviour comes from the file named
by HANDOVER_TEST_MODE, read once at import, as a new release's code is: ok | broken | unhealthy."""
import asyncio
import json
import os

MODE = open(os.environ['HANDOVER_TEST_MODE']).read().strip()
if MODE == 'broken':
    raise RuntimeError('this release cannot start')
LOG = os.environ.get('HANDOVER_TEST_LOG')


async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            message = await receive()
            if message['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            else:
                await send({'type': 'lifespan.shutdown.complete'})
                return
    path = scope['path']
    if path.startswith('/slow/'):
        await asyncio.sleep(float(path.rsplit('/', 1)[1]))
    body = json.dumps(dict(status='degraded' if MODE == 'unhealthy' else 'ok', neo4j='connected',
                           evidence_engine='ok', mode=MODE, server=os.getppid(),
                           process=dict(pid=os.getpid(), parent=os.getppid(), one_owner=True))).encode()
    await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
    await send({'type': 'http.response.body', 'body': body})
