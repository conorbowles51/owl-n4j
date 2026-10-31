"""Without NEO4J_PASSWORD the backend never contacts Neo4j: a guessed password counts as a failed login on the
live server and locks the neo4j user out for the live app too (lx-datastores, 31 Oct)."""
import importlib
import os
import unittest
from pathlib import Path
from unittest import mock

from neo4j.exceptions import AuthError

BACKEND = Path(__file__).resolve().parents[1]


class NoPasswordTest(unittest.TestCase):
    def test_config_has_no_password_default(self):
        import config
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('NEO4J_PASSWORD', None)
            with mock.patch('dotenv.load_dotenv'), mock.patch.object(Path, 'exists', return_value=False):
                fresh = importlib.reload(config)
            try:
                self.assertIsNone(fresh.NEO4J_PASSWORD)
            finally:
                importlib.reload(config)

    def test_open_driver_refuses_without_connecting(self):
        module = importlib.import_module("services.neo4j.driver")
        with mock.patch.object(module, 'NEO4J_PASSWORD', None), \
                mock.patch.object(module.GraphDatabase, 'driver') as real:
            refusing = module.open_driver()
            with self.assertRaises(AuthError):
                refusing.session()
            with self.assertRaises(AuthError):
                refusing.verify_connectivity()
            refusing.close()
        real.assert_not_called()

    def test_open_driver_uses_the_configured_password(self):
        module = importlib.import_module("services.neo4j.driver")
        with mock.patch.object(module, 'NEO4J_PASSWORD', 'secret'), \
                mock.patch.object(module.GraphDatabase, 'driver') as real:
            module.open_driver()
        real.assert_called_once_with(module.NEO4J_URI, auth=(module.NEO4J_USER, 'secret'))

    def test_every_backend_driver_goes_through_open_driver(self):
        direct = []
        for path in BACKEND.rglob('*.py'):
            if 'tests' in path.parts or 'scripts' in path.parts or '.venv' in path.parts:
                continue
            text = path.read_text(errors='replace')
            if 'GraphDatabase.driver(' in text and path.name != 'driver.py':
                direct.append(str(path.relative_to(BACKEND)))
        self.assertEqual(direct, [])


if __name__ == '__main__':
    unittest.main()
