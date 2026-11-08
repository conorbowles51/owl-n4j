"""Host policy memory floors (deploy/hostpolicy).

memory.low is best effort: on 1 Nov 00:16 the kernel swapped 1.4 GB of the live backend out while it used 3.6 GB,
under its 6G memory.low, and request threads stalled 5-6 s on swap-in. Live services that must stay in RAM carry a
hard floor (MemoryMin), and every parent slice carries at least the sum of its children's floors, because a child's
effective memory.min is capped by its parents'.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

POLICY = Path(__file__).resolve().parents[2] / 'deploy' / 'hostpolicy'
# The Neo4j container scope is transient; headless/hostpolicy-sweep.sh gives it memory.min 5G.
NEO4J_MIN = 5 * 1024 ** 3
UNITS = {'G': 1024 ** 3, 'M': 1024 ** 2, 'K': 1024}


def _setting(path, key):
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith(key + '='):
            value = line.split('=', 1)[1].strip()
            return int(value[:-1]) * UNITS[value[-1]] if value[-1] in UNITS else int(value)
    return 0


class HostPolicyMemoryFloors(unittest.TestCase):
    def test_backend_has_a_hard_floor_at_its_protection(self):
        conf = POLICY / 'owl-backend-v2.service.d' / '50-lx-hostpolicy.conf'
        low = _setting(conf, 'MemoryLow')
        self.assertGreater(low, 0)
        self.assertGreaterEqual(_setting(conf, 'MemoryMin'), low)

    def test_live_slices_carry_the_sum_of_child_floors(self):
        children = NEO4J_MIN + _setting(POLICY / 'owl-backend-v2.service.d' / '50-lx-hostpolicy.conf', 'MemoryMin')
        for unit in ('loupe-live.slice', 'loupe.slice'):
            self.assertGreaterEqual(_setting(POLICY / unit, 'MemoryMin'), children, unit)

    def test_floors_leave_the_slice_protection_above_them(self):
        for unit in ('loupe-live.slice', 'loupe.slice'):
            self.assertGreaterEqual(_setting(POLICY / unit, 'MemoryLow'), _setting(POLICY / unit, 'MemoryMin'), unit)


class InstallAppliesToRunningUnits(unittest.TestCase):
    """daemon-reload alone left a new MemoryMin at 0 on the running backend and slices (1 Nov)."""

    def test_install_sets_the_floors_on_running_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = Path(tmp) / 'calls'
            stub = Path(tmp) / 'systemctl'
            stub.write_text('#!/bin/sh\necho "$@" >> %s\nexit 0\n' % calls)
            stub.chmod(0o755)
            dest = Path(tmp) / 'units'
            dest.mkdir()
            env = dict(os.environ, SYSTEMCTL=str(stub), HOSTPOLICY_UNIT_DIR=str(dest))
            subprocess.run(['bash', str(POLICY / 'install.sh')], env=env, check=True, capture_output=True)
            lines = calls.read_text().splitlines()
        self.assertIn('daemon-reload', lines)
        backend = [l for l in lines if l.startswith('set-property --runtime owl-backend-v2.service ')]
        self.assertEqual(len(backend), 1, lines)
        self.assertIn('MemoryMin=8G', backend[0].split())  # Neil 8 Nov: the app memory guarantee
        self.assertIn('MemoryLow=8G', backend[0].split())
        for unit in ('loupe.slice', 'loupe-live.slice'):
            line = [l for l in lines if l.startswith('set-property --runtime %s ' % unit)]
            self.assertEqual(len(line), 1, lines)
            self.assertIn('MemoryMin=13G', line[0].split())
            self.assertIn('MemoryLow=17G', line[0].split())


    def test_a_drop_in_without_resource_lines_does_not_stop_the_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'policy'
            subprocess.run(['cp', '-r', str(POLICY), str(src)], check=True)
            (src / 'aa.service.d').mkdir()
            (src / 'aa.service.d' / '50-lx-hostpolicy.conf').write_text('[Service]\nSlice=x.slice\n')
            calls = Path(tmp) / 'calls'
            stub = Path(tmp) / 'systemctl'
            stub.write_text('#!/bin/sh\necho "$@" >> %s\nexit 0\n' % calls)
            stub.chmod(0o755)
            (Path(tmp) / 'units').mkdir()
            env = dict(os.environ, SYSTEMCTL=str(stub), HOSTPOLICY_UNIT_DIR=str(Path(tmp) / 'units'))
            subprocess.run(['bash', str(src / 'install.sh')], env=env, check=True, capture_output=True)
            self.assertTrue(any(l.startswith('set-property --runtime owl-backend-v2.service ')
                                for l in calls.read_text().splitlines()))

    def test_remove_clears_the_runtime_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp) / 'control'
            for unit in ('loupe.slice', 'owl-backend-v2.service'):
                (control / (unit + '.d')).mkdir(parents=True)
                (control / (unit + '.d') / '50-MemoryMin.conf').write_text('x')
            (control / 'loupe.slice.d' / '50-Other.conf').write_text('x')
            stub = Path(tmp) / 'systemctl'
            stub.write_text('#!/bin/sh\nexit 0\n')
            stub.chmod(0o755)
            (Path(tmp) / 'units').mkdir()
            env = dict(os.environ, SYSTEMCTL=str(stub), HOSTPOLICY_UNIT_DIR=str(Path(tmp) / 'units'),
                       HOSTPOLICY_CONTROL_DIR=str(control))
            subprocess.run(['bash', str(POLICY / 'install.sh'), '--remove'], env=env, check=True, capture_output=True)
            self.assertFalse((control / 'loupe.slice.d' / '50-MemoryMin.conf').exists())
            self.assertFalse((control / 'owl-backend-v2.service.d' / '50-MemoryMin.conf').exists())
            self.assertTrue((control / 'loupe.slice.d' / '50-Other.conf').exists())


if __name__ == '__main__':
    unittest.main()
