"""The live service ranks above the jobs fleet on the host (lx-hostpolicy, WS-A): the live containers run in
loupe-live.slice with protected memory, the live units move into that slice, and the protection fits in it."""
import configparser
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'deploy' / 'hostpolicy'
LIVE_CONTAINERS = {'neo4j': 'owl-v2-n4j', 'postgres': 'owl-v2-pg', 'redis': 'owl-v2-redis'}
UNITS = {'K': 1024, 'M': 1024 ** 2, 'G': 1024 ** 3}


def _bytes(value):
    m = re.fullmatch(r'(\d+)([kKmMgG]?)', str(value).strip())
    assert m, value
    return int(m.group(1)) * UNITS.get(m.group(2).upper(), 1)


def _unit(path):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(path)
    return parser


def test_live_containers_run_in_the_live_slice_with_reserved_memory():
    services = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']
    for service, name in LIVE_CONTAINERS.items():
        assert services[service]['container_name'] == name
        assert services[service].get('cgroup_parent') == 'loupe-live.slice', service
        assert _bytes(services[service]['mem_reservation']) > 0, service


def test_live_units_move_into_the_live_slice_and_the_fleet_runs_idle():
    for unit in ('owl-backend-v2.service', 'owl-frontend-v2.service'):
        assert _unit(POLICY / f'{unit}.d' / '50-lx-hostpolicy.conf')['Service']['Slice'] == 'loupe-live.slice'
    for slice_ in ('loupe.slice', 'loupe-live.slice'):
        assert int(_unit(POLICY / slice_)['Slice']['CPUWeight']) >= 1000
    watchdog = _unit(POLICY / 'fin-watchdog.service.d' / '50-lx-hostpolicy.conf')['Service']
    assert watchdog['CPUWeight'] == 'idle' and 'Slice' not in watchdog
    assert 'MemoryHigh' in watchdog and 'MemorySwapMax' in watchdog
    assert _unit(POLICY / 'fleet.slice')['Slice']['CPUWeight'] == 'idle'


def test_live_protection_fits_inside_the_live_slice():
    services = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']
    total = sum(_bytes(services[s]['mem_reservation']) for s in LIVE_CONTAINERS)
    total += sum(_bytes(_unit(POLICY / f'{u}.d' / '50-lx-hostpolicy.conf')['Service']['MemoryLow'])
                 for u in ('owl-backend-v2.service', 'owl-frontend-v2.service'))
    for slice_ in ('loupe.slice', 'loupe-live.slice'):
        assert total <= _bytes(_unit(POLICY / slice_)['Slice']['MemoryLow']), slice_


def test_installer_installs_and_removes_every_file(tmp_path):
    env = {'HOSTPOLICY_UNIT_DIR': str(tmp_path), 'SYSTEMCTL': 'true', 'PATH': '/usr/bin:/bin'}
    subprocess.run(['bash', str(POLICY / 'install.sh')], env=env, check=True)
    installed = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*') if p.is_file())
    shipped = sorted(str(p.relative_to(POLICY)) for p in POLICY.rglob('*') if p.is_file() and p.name != 'install.sh')
    assert installed == shipped
    subprocess.run(['bash', str(POLICY / 'install.sh'), '--remove'], env=env, check=True)
    assert not [p for p in tmp_path.rglob('*') if p.is_file()]
