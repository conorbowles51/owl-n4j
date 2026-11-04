"""lx-matchgrades F: read-only timing of the agent's get_transfer_pairs body on one case."""
import sys, time, json
sys.path.insert(0, '.')
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.orm import Session
from postgres.session import _get_engine
from services.agent import match_tools as M
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY")); s = Session(bind=c)
    t = time.time(); out = M.transfer_pairs(s, UUID(sys.argv[1]), limit=100)
    print(json.dumps(dict(seconds=round(time.time() - t, 1), total=out['total'], returned=out['returned'], by=out['by_strength'], left=out['left_out_words'])))
    c.rollback()
