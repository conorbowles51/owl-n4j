"""Per-minute host load and a 10-second availability probe, written to Postgres.

Runs as one small always-on process (deploy/loupe-host-recorder.service), outside the backend: it imports
nothing from the app, only the standard library and psycopg, so it costs a few milliseconds of CPU a minute
and keeps recording while the backend is restarting or stuck.

Every minute, one ``host_load_minute`` row (migration 20261031_lx_measure):
  * load average, busy CPU cores, host pressure (cpu/memory/io, "some" and "full", as % of the minute);
  * memory available, swap used, pages swapped in and out in the minute;
  * ``groups``: per cgroup (depth 1 to 3: slices, services, docker scopes named by container; loupe.slice is the
    live app, fleet.slice and system.slice/fin-watchdog.service the jobs fleet): CPU cores,
    CPU and IO pressure (% of the minute), memory and swap in MB;
  * ``top``: the 5 processes that used the most CPU in the minute (pid, name, cores, nice, cgroup);
  * ``recorder_cpu_ms``: this process's own CPU in the minute, so its cost is measured, not assumed.
A watchdog thread exits the process (systemd restarts it) if the loop stalls for 5 minutes.
Every 10 seconds, one ``availability_probe`` row per target: the app page (``app``) and ``/api/health``
(``api``) on the address people open, with status, time and bytes, or the error.

All figures are deltas of kernel counters over the measured interval (``interval_s``), so a late sample is
still exact. Rows are kept 90 days. A database outage keeps up to 2 hours in memory and retries.

    python scripts/host_recorder.py            # run (DATABASE_URL from the environment)
    python scripts/host_recorder.py --once     # print one sample as JSON and exit (no database)
"""
import argparse
import json
import os
import re
import resource
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

CGROUP = '/sys/fs/cgroup'
PROBE_BASE = os.environ.get('LOUPE_PROBE_BASE', 'http://104.196.62.215:5174')
PROBES = (('app', '/'), ('api', '/api/health'))
PROBE_SECONDS = 10
PROBE_TIMEOUT = 9
KEEP_DAYS = 90
MAX_BUFFER_MINUTES = 120
TOP = 5
GROUP_MIN_CORES = 0.01
GROUP_MIN_MB = 100
CLK = os.sysconf('SC_CLK_TCK')
PAGE_MB = os.sysconf('SC_PAGE_SIZE') / 2 ** 20
_DOCKER = re.compile(r'^docker-([0-9a-f]{64})\.scope$')


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _pressure(path):
    """{'some': total_us, 'full': total_us} from a pressure file, or {}."""
    text = _read(path)
    out = {}
    for line in (text or '').splitlines():
        parts = line.split()
        if parts and parts[0] in ('some', 'full'):
            for part in parts[1:]:
                if part.startswith('total='):
                    out[parts[0]] = int(part[6:])
    return out


def _cpu_usage_us(group):
    for line in (_read(f'{group}/cpu.stat') or '').splitlines():
        if line.startswith('usage_usec '):
            return int(line.split()[1])
    return None


def _mb(path):
    text = _read(path)
    try:
        return int(text) / 2 ** 20 if text and text.strip() != 'max' else None
    except ValueError:
        return None


class Names:
    """Docker scope -> container name, refreshed at most every 10 minutes when an unknown scope appears."""

    def __init__(self):
        self.names, self.loaded = {}, 0.0

    def of(self, rel):
        base = rel.rsplit('/', 1)[-1]
        match = _DOCKER.match(base)
        if not match:
            return rel
        cid = match.group(1)
        if cid not in self.names and time.monotonic() - self.loaded > 600:
            self.loaded = time.monotonic()
            try:
                out = subprocess.run(['docker', 'ps', '--no-trunc', '--format', '{{.ID}} {{.Names}}'],
                                     capture_output=True, text=True, timeout=10).stdout
                self.names = dict(line.split(' ', 1) for line in out.splitlines() if ' ' in line)
            except Exception:
                pass
        name = self.names.get(cid)
        return rel.rsplit('/', 1)[0] + f'/docker:{name}' if name else rel


def _groups(max_depth=3):
    """Relative cgroup path -> counters, down to ``max_depth`` (loupe.slice/loupe-live.slice/<service> is 3)."""
    out = {}

    def walk(rel, depth):
        full = f'{CGROUP}/{rel}' if rel else CGROUP
        try:
            children = [e for e in os.listdir(full) if os.path.isdir(f'{full}/{e}')]
        except OSError:
            return
        for e in children:
            child = f'{rel}/{e}' if rel else e
            path = f'{CGROUP}/{child}'
            usage = _cpu_usage_us(path)
            if usage is None:
                continue
            out[child] = dict(cpu_us=usage, cpu_p=_pressure(f'{path}/cpu.pressure'), io_p=_pressure(f'{path}/io.pressure'),
                              mem_mb=_mb(f'{path}/memory.current'), swap_mb=_mb(f'{path}/memory.swap.current'))
            if depth < max_depth:
                walk(child, depth + 1)
    walk('', 1)
    return out


def _procs():
    """pid -> (ticks, comm, nice)."""
    out = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        text = _read(f'/proc/{pid}/stat')
        if not text:
            continue
        right = text.rfind(')')
        fields = text[right + 2:].split()
        try:
            out[int(pid)] = (int(fields[11]) + int(fields[12]), text[text.find('(') + 1:right], int(fields[16]))
        except (IndexError, ValueError):
            continue
    return out


def _command(pid):
    """The program and its first plain arguments (never a value with '=', '@' or ':' that could be a secret)."""
    raw = _read(f'/proc/{pid}/cmdline') or ''
    args = [a for a in raw.split('\0') if a]
    if not args:
        return None
    words = [os.path.basename(args[0])]
    for a in args[1:]:
        if len(words) >= 4:
            break
        if any(c in a for c in '=@:') or len(a) > 80:
            continue
        words.append(os.path.basename(a) if '/' in a and not a.startswith('-') else a)
    return ' '.join(words)[:120]


def _cgroup_of(pid):
    text = _read(f'/proc/{pid}/cgroup') or ''
    return text.strip().split('::', 1)[-1][:120] if text else None


def _host():
    stat = (_read('/proc/stat') or '').splitlines()[0].split()[1:]
    ticks = [int(x) for x in stat]
    idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
    vm = dict(line.split() for line in (_read('/proc/vmstat') or '').splitlines() if line.count(' ') == 1)
    mem = {}
    for line in (_read('/proc/meminfo') or '').splitlines():
        name, _, rest = line.partition(':')
        mem[name] = int(rest.split()[0]) / 1024 if rest.split() else 0
    return dict(busy=sum(ticks[:8]) - idle, cpu_p=_pressure('/proc/pressure/cpu'), mem_p=_pressure('/proc/pressure/memory'),
                io_p=_pressure('/proc/pressure/io'), swpin=int(vm.get('pswpin', 0)), swpout=int(vm.get('pswpout', 0)),
                mem_available=mem.get('MemAvailable'), swap_used=(mem.get('SwapTotal', 0) - mem.get('SwapFree', 0)),
                load1=float((_read('/proc/loadavg') or '0').split()[0]))


def _self_cpu():
    a, b = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime + a.ru_stime + b.ru_utime + b.ru_stime


def _pct(new, old, key, seconds):
    if key not in new or key not in old or seconds <= 0:
        return None
    return round(max(0, new[key] - old[key]) / 1e6 / seconds * 100, 2)


class Sampler:
    def __init__(self):
        self.names = Names()
        self.prev = None

    def take(self):
        return dict(mono=time.monotonic(), wall=time.time(), host=_host(), groups=_groups(), procs=_procs(),
                    self_cpu=_self_cpu())

    def sample(self):
        """One row for the interval since the previous call, or None the first time."""
        now = self.take()
        prev, self.prev = self.prev, now
        if prev is None:
            return None
        seconds = now['mono'] - prev['mono']
        h, p = now['host'], prev['host']
        groups = {}
        for rel, g in now['groups'].items():
            old = prev['groups'].get(rel)
            if old is None:
                continue
            cores = max(0, g['cpu_us'] - old['cpu_us']) / 1e6 / seconds
            if cores < GROUP_MIN_CORES and (g['mem_mb'] or 0) < GROUP_MIN_MB:
                continue
            groups[self.names.of(rel)] = dict(
                cores=round(cores, 3), cpu_some=_pct(g['cpu_p'], old['cpu_p'], 'some', seconds),
                cpu_full=_pct(g['cpu_p'], old['cpu_p'], 'full', seconds), io_some=_pct(g['io_p'], old['io_p'], 'some', seconds),
                mem_mb=round(g['mem_mb'], 1) if g['mem_mb'] is not None else None,
                swap_mb=round(g['swap_mb'], 1) if g['swap_mb'] is not None else None)
        used = []
        for pid, (ticks, comm, nice) in now['procs'].items():
            old = prev['procs'].get(pid)
            delta = ticks - old[0] if old and old[1] == comm else None
            if delta and delta > 0:
                used.append((delta, pid, comm, nice))
        used.sort(reverse=True)
        top = [dict(pid=pid, comm=comm, cmd=_command(pid), nice=nice, cores=round(delta / CLK / seconds, 3),
                    cgroup=_cgroup_of(pid)) for delta, pid, comm, nice in used[:TOP]]
        middle = (now['wall'] + prev['wall']) / 2  # the minute the interval covers (samples sit just after each minute)
        return dict(
            minute=datetime.fromtimestamp(middle - middle % 60, tz=timezone.utc), interval_s=round(seconds, 3),
            load1=h['load1'], cpu_busy_cores=round((h['busy'] - p['busy']) / CLK / seconds, 3),
            psi_cpu_some=_pct(h['cpu_p'], p['cpu_p'], 'some', seconds), psi_cpu_full=_pct(h['cpu_p'], p['cpu_p'], 'full', seconds),
            psi_mem_some=_pct(h['mem_p'], p['mem_p'], 'some', seconds), psi_mem_full=_pct(h['mem_p'], p['mem_p'], 'full', seconds),
            psi_io_some=_pct(h['io_p'], p['io_p'], 'some', seconds), psi_io_full=_pct(h['io_p'], p['io_p'], 'full', seconds),
            mem_available_mb=round(h['mem_available'], 1) if h['mem_available'] is not None else None,
            swap_used_mb=round(h['swap_used'], 1), swap_in_pages=h['swpin'] - p['swpin'], swap_out_pages=h['swpout'] - p['swpout'],
            groups=groups, top=top, recorder_cpu_ms=round((now['self_cpu'] - prev['self_cpu']) * 1000, 2))


def probe(target, path, base=PROBE_BASE, timeout=PROBE_TIMEOUT):
    at = datetime.now(timezone.utc)
    started = time.perf_counter()
    status, size, error = None, None, None
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, headers={'User-Agent': 'loupe-host-recorder'}),
                                    timeout=timeout) as response:
            status, size = response.status, len(response.read())
    except urllib.error.HTTPError as e:
        status, size = e.code, None
    except Exception as e:  # refused, timeout, reset: the app was not reachable
        error = f'{type(e).__name__}: {e}'[:120]
    return dict(at=at, target=target, status=status, ms=round((time.perf_counter() - started) * 1000, 2), bytes=size,
                error=error)


def probe_all():
    results = [None] * len(PROBES)

    def one(i, target, path):
        results[i] = probe(target, path)
    threads = [threading.Thread(target=one, args=(i, t, p), daemon=True) for i, (t, p) in enumerate(PROBES)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(PROBE_TIMEOUT + 2)
    return [r for r in results if r]


INSERT_HOST = '''
INSERT INTO host_load_minute (minute, interval_s, load1, cpu_busy_cores, psi_cpu_some, psi_cpu_full, psi_mem_some,
  psi_mem_full, psi_io_some, psi_io_full, mem_available_mb, swap_used_mb, swap_in_pages, swap_out_pages, groups, top,
  recorder_cpu_ms)
VALUES (%(minute)s, %(interval_s)s, %(load1)s, %(cpu_busy_cores)s, %(psi_cpu_some)s, %(psi_cpu_full)s, %(psi_mem_some)s,
  %(psi_mem_full)s, %(psi_io_some)s, %(psi_io_full)s, %(mem_available_mb)s, %(swap_used_mb)s, %(swap_in_pages)s,
  %(swap_out_pages)s, %(groups)s, %(top)s, %(recorder_cpu_ms)s)
ON CONFLICT (minute) DO NOTHING
'''
INSERT_PROBE = '''
INSERT INTO availability_probe (at, target, status, ms, bytes, error)
VALUES (%(at)s, %(target)s, %(status)s, %(ms)s, %(bytes)s, %(error)s)
'''
PRUNE = (f"DELETE FROM host_load_minute WHERE minute < now() - interval '{KEEP_DAYS} days'",
         f"DELETE FROM availability_probe WHERE at < now() - interval '{KEEP_DAYS} days'")


def database_url():
    url = os.environ.get('DATABASE_URL') or ''
    return re.sub(r'^postgresql\+\w+://', 'postgresql://', url)


class Store:
    def __init__(self, url):
        self.url, self.conn = url, None
        self.lock = threading.Lock()
        self.hosts, self.probes = [], []
        self.pruned = 0.0
        self.last_warning = 0.0

    def add(self, host=None, probes=()):
        with self.lock:
            self._add(host, probes)

    def _add(self, host, probes):
        if host:
            self.hosts.append(host)
        self.probes.extend(probes)
        self.hosts = self.hosts[-MAX_BUFFER_MINUTES:]
        self.probes = self.probes[-MAX_BUFFER_MINUTES * 6 * len(PROBES):]

    def flush(self):
        import psycopg
        from psycopg.types.json import Jsonb
        with self.lock:  # rows added by the probe thread during the write wait for the next flush
            hosts, probes, self.hosts, self.probes = self.hosts, self.probes, [], []
        try:
            if self.conn is None or self.conn.closed:
                # Keepalives and a TCP user timeout end a write to a database that stopped answering.
                self.conn = psycopg.connect(self.url, connect_timeout=5, application_name='loupe-host-recorder',
                                            keepalives=1, keepalives_idle=10, keepalives_interval=5,
                                            keepalives_count=3, tcp_user_timeout=30000)
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '10s'")
                for h in hosts:
                    cur.execute(INSERT_HOST, dict(h, groups=Jsonb(h['groups']), top=Jsonb(h['top'])))
                if probes:
                    cur.executemany(INSERT_PROBE, probes)
                if time.time() - self.pruned > 86400:
                    for statement in PRUNE:
                        cur.execute(statement)
                    self.pruned = time.time()
        except Exception as e:
            with self.lock:
                for h in reversed(hosts):
                    self.hosts.insert(0, h)
                self.probes[:0] = probes
                self._add(None, ())  # re-apply the caps
            try:
                if self.conn is not None:
                    self.conn.close()
            except Exception:
                pass
            self.conn = None
            if time.time() - self.last_warning > 600:
                self.last_warning = time.time()
                print(f'host recorder: could not save, will retry ({type(e).__name__}: {str(e)[:200]})', flush=True)


STALL_SECONDS = 300


def watchdog(progress, stall=STALL_SECONDS):
    """Exit (systemd restarts the unit) if the main loop has made no progress for ``stall`` seconds, e.g. a
    database write that never returns; a stuck recorder would otherwise look alive and record nothing."""
    while True:
        time.sleep(stall / 5)
        if time.monotonic() - min(progress) > stall:
            print(f'host recorder: no progress for {stall} s, exiting to be restarted', flush=True)
            os._exit(3)


def probe_forever(store, progress):
    """Every PROBE_SECONDS on its own thread, so a slow probe never delays or skips a minute's host row."""
    while True:
        tick = time.monotonic()
        progress[1] = tick
        store.add(probes=probe_all())
        time.sleep(max(0.5, PROBE_SECONDS - (time.monotonic() - tick)))


def run(url):
    sampler, store = Sampler(), Store(url)
    sampler.sample()
    progress = [time.monotonic(), time.monotonic()]  # host loop, probe loop
    threading.Thread(target=watchdog, args=(progress,), daemon=True).start()
    threading.Thread(target=probe_forever, args=(store, progress), daemon=True).start()
    while True:
        progress[0] = time.monotonic()
        time.sleep(max(0.1, 60.2 - time.time() % 60))  # just after each minute
        store.add(host=sampler.sample())
        store.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--once', action='store_true', help='print one 5-second sample and one probe round, then exit')
    args = parser.parse_args(argv)
    if args.once:
        sampler = Sampler()
        sampler.sample()
        time.sleep(5)
        print(json.dumps(dict(host=sampler.sample(), probes=probe_all()), default=str, indent=1))
        return 0
    url = database_url()
    if not url:
        print('host recorder: DATABASE_URL is not set', file=sys.stderr)
        return 2
    run(url)


if __name__ == '__main__':
    sys.exit(main())
