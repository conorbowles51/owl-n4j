"""Private durable phone-report checkpoints and cross-job report exclusion."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from app.config import settings
from app.services.ingestion_checkpoints import atomic_json, current_checkpoint_root


def source_digest(path, boundary):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
            boundary(); digest.update(chunk)
    return digest.hexdigest()


class Recovery:
    def __init__(self, xml_path, boundary):
        root = current_checkpoint_root()
        self.path = root / 'phone-report.json' if root else None
        self.state = json.loads(self.path.read_text()) if self.path and self.path.exists() else {}
        identity = {'format': 'phone-recovery-v1', 'source_sha256': source_digest(xml_path, boundary), 'source_path': str(xml_path.resolve())}
        if self.state and any(self.state.get(key) != value for key, value in identity.items()):
            raise ValueError('The phone report source has changed since processing paused. Keep the original source to resume.')
        self.state.update(identity)
        self.state.setdefault('run_id', str(uuid4()))

    def save(self, **values):
        self.state.update(values)
        if self.path: atomic_json(self.path, self.state)


@contextmanager
def report_lock(case_id, report_key, boundary):
    key = hashlib.sha256(f'{case_id}:{report_key}'.encode()).hexdigest()
    root = Path(settings.storage_path) / '_checkpoints' / '_phone_locks'
    root.mkdir(parents=True, exist_ok=True)
    with (root / (key + '.lock')).open('a') as lock:
        while True:
            boundary()
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(.25)
        try: yield
        finally: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def writer_state(writer):
    return {key: sorted(value) if isinstance(value, set) else value
        for key, value in vars(writer).items()
        if key.endswith('_created') or key.endswith('_total') or key in {
            '_created_person_keys', '_created_node_keys'}}


def restore_writer(writer, state):
    allowed = set(writer_state(writer))
    for key, value in state.items():
        if key in allowed:
            setattr(writer, key, set(value) if key.startswith('_created_') else value)
