#!/usr/bin/env python3
"""The backend unit's main process when deploy/backend-restart.conf says "handover" (deploy/backend-handover.sh).

A backend restart makes requests wait for as long as the new workers take to start (49-74 s on 4 Nov). This process
stays up across a release and runs the backend as generations, every one serving the socket systemd holds on fd 3:

  SIGUSR2  start the next generation beside the running one. Its workers take requests from the same socket as soon
           as they are up, so nothing moves and no request is refused. It is "ready" once /health, asked through the
           real port, has answered healthy from each of its workers. Until then the old generation keeps serving, and
           a generation that dies or stays unhealthy is stopped: the old one has not been touched.
  SIGHUP   commit: stop the old generation. It stops taking requests at once and finishes the ones in flight, within
           the same bounds as a service stop.
  SIGQUIT  abort: stop the new generation. So does the commit deadline, when a release dies after the start.

The whole unit stays one unit: the same cgroup, memory floor, journal and main process. Python's standard library only,
run with -I from a copy outside the checkout (a rollback to a commit without this file must still start).

Every step is written to the state file as it happens; deploy/backend-handover.sh reads it.
"""
import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

LISTEN_FD = 3


class Generation:
    def __init__(self, command):
        # A session of its own: the group is what a stop signals, as a service stop signals the whole unit.
        self.process = subprocess.Popen(command, pass_fds=(LISTEN_FD,), start_new_session=True)
        self.pid = self.process.pid

    def signal(self, signum):
        try:
            os.killpg(self.pid, signum)
        except ProcessLookupError:
            pass

    def running(self):
        return self.process.poll() is None

    def group_alive(self):
        try:
            os.killpg(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def healthy(body):
    """The release health check's meaning of healthy (deploy.sh release_is_healthy), plus one owner per loop."""
    if body.get('status') != 'ok':
        return False
    if str(body.get('neo4j', '')).startswith('error:'):
        return False
    engine = str(body.get('evidence_engine', ''))
    if engine.startswith('error:') or engine == 'unavailable':
        return False
    return bool((body.get('process') or {}).get('one_owner'))


class HealthWatch(threading.Thread):
    """Asks /health through the real port until each worker of the new generation has answered healthy. The answers
    come from whichever worker takes the connection, old or new: only the new ones count."""

    def __init__(self, url, server_pid, workers, pause):
        super().__init__(daemon=True, name='health-watch')
        self.url, self.server_pid, self.workers, self.pause = url, server_pid, workers, pause
        self.seen = set()
        self.last_answer = None
        self.done = threading.Event()
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set() and len(self.seen) < self.workers:
            try:
                with urllib.request.urlopen(self.url, timeout=15) as response:
                    body = json.loads(response.read())
                process = body.get('process') or {}
                if process.get('parent') == self.server_pid:
                    self.last_answer = {key: body.get(key) for key in ('status', 'neo4j', 'evidence_engine', 'postgres')}
                    self.last_answer['one_owner'] = process.get('one_owner')
                    if healthy(body):
                        self.seen.add(process.get('pid'))
            except Exception as error:  # noqa: BLE001 - not up yet, or a worker busy: asked again
                self.last_answer = {'error': type(error).__name__}
            self.stop.wait(self.pause)
        if len(self.seen) >= self.workers:
            self.done.set()


class Supervisor:
    def __init__(self, options):
        self.options = options
        self.command = options.command
        self.signals = []
        self.current = None
        self.next = None
        self.watch = None
        self.commit_by = None
        self.old = None
        self.old_step = None
        self.stopping_new = None
        self.count = 0
        self.handover = None
        self.started_at = time.time()
        self.health_url = self._health_url()
        with open(os.path.abspath(sys.argv[0]), 'rb') as handle:
            self.script_sha = hashlib.sha256(handle.read()).hexdigest()

    @staticmethod
    def _health_url():
        probe = socket.socket(fileno=os.dup(LISTEN_FD))
        try:
            host, port = probe.getsockname()[:2]
        finally:
            probe.close()
        return f'http://{"127.0.0.1" if host in ("0.0.0.0", "::") else host}:{port}/health'

    def write_state(self):
        state = dict(pid=os.getpid(), script_sha=self.script_sha, started_at=self.started_at,
                     server_pid=self.current.pid if self.current else None, handovers=self.count,
                     handover=self.handover)
        temporary = f'{self.options.state}.{os.getpid()}.tmp'
        with open(temporary, 'w') as handle:
            json.dump(state, handle)
        os.chmod(temporary, 0o644)
        os.replace(temporary, self.options.state)

    def say(self, line):
        print(f'[backend-supervisor] {line}', flush=True)

    def phase(self, name, **values):
        self.handover.update(phase=name, **values)
        self.handover[f'{name}_at'] = time.time()
        self.write_state()
        self.say(f'handover {self.handover["id"]}: {name} {values if values else ""}')

    # --- signals -------------------------------------------------------------------------------------------------

    def install(self):
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR2, signal.SIGHUP, signal.SIGQUIT):
            signal.signal(signum, lambda number, _frame: self.signals.append(number))

    def take_signal(self, signum):
        if signum in (signal.SIGTERM, signal.SIGINT):
            return self.stop_everything(signum)
        if signum == signal.SIGUSR2:
            self.begin()
        elif signum == signal.SIGHUP:
            self.commit()
        elif signum == signal.SIGQUIT:
            self.abort('aborted by the release')
        return None

    # --- the handover --------------------------------------------------------------------------------------------

    def begin(self):
        if self.next is not None or self.old is not None:
            self.say('a handover is already open; ignored')
            return
        self.count += 1
        self.handover = dict(id=self.count, phase='starting', starting_at=time.time(), old_server_pid=self.current.pid)
        self.write_state()
        try:
            self.next = Generation(self.command)
        except OSError as error:
            self.next = None
            self.phase('failed', reason=f'could not start: {error}')
            return
        self.handover['new_server_pid'] = self.next.pid
        self.watch = HealthWatch(self.health_url, self.next.pid, self.options.workers, self.options.health_pause)
        self.watch.start()
        self.write_state()
        self.say(f'handover {self.count}: next backend started, server pid {self.next.pid}')

    def fail_next(self, reason):
        """The old generation keeps serving; it was never told anything."""
        if self.watch:
            self.watch.stop.set()
        generation, self.next, self.watch, self.commit_by = self.next, None, None, None
        self.phase('failed', reason=reason)
        if generation is not None:
            generation.signal(signal.SIGTERM)
            self.stopping_new = (generation, time.monotonic(), 0)

    def abort(self, reason):
        if self.next is not None and self.old is None:
            self.fail_next(reason)

    def commit(self):
        if self.next is None or self.old is not None or self.handover.get('phase') != 'ready':
            self.say('nothing ready to commit; ignored')
            return
        self.commit_by = None
        self.old, self.current, self.next = self.current, self.next, None
        self.watch = None
        self.old_step = (0, time.monotonic())
        self.old.signal(signal.SIGTERM)
        self.phase('stopping_old')

    def tick_handover(self):
        now = time.monotonic()
        if self.next is not None:
            if not self.next.running():
                self.fail_next(f'the new backend ended with status {self.next.process.returncode}')
            elif self.handover['phase'] == 'starting':
                if self.watch.done.is_set():
                    self.commit_by = now + self.options.commit_seconds
                    self.phase('ready', workers=len(self.watch.seen))
                elif now - self.handover_clock() > self.options.ready_seconds:
                    self.fail_next(f'not healthy after {self.options.ready_seconds:.0f} s: {self.watch.last_answer}')
            elif self.commit_by is not None and now > self.commit_by:
                self.fail_next(f'no commit within {self.options.commit_seconds:.0f} s')
        self.tick_old(now)
        self.tick_stopping_new(now)

    def handover_clock(self):
        # time.monotonic() when the handover began, from the wall clock it was written with.
        return time.monotonic() - (time.time() - self.handover['starting_at'])

    def tick_old(self, now):
        """The bounds of backend-stop.sh: SIGTERM, then SIGINT (uvicorn's force-quit), then SIGKILL."""
        if self.old is None:
            return
        step, since = self.old_step
        if self.old.running():
            if step == 0 and now - since > self.options.stop_seconds:
                self.old.signal(signal.SIGINT)
                self.old_step = (1, now)
                self.handover['escalated'] = 'sigint'
            elif step == 1 and now - since > self.options.sigint_seconds:
                self.old.signal(signal.SIGKILL)
                self.old_step = (2, now)
                self.handover['escalated'] = 'sigkill'
            return
        # The server process has gone; what is left of its group ends as a service stop would end it.
        if self.old.group_alive() and step < 3:
            self.old_step = (3, now)
            return
        if self.old.group_alive():
            if now - since < self.options.leftover_seconds:
                return
            self.old.signal(signal.SIGKILL)
        self.old, self.old_step = None, None
        self.handover['old_stopped_at'] = time.time()
        self.phase('done')

    def tick_stopping_new(self, now):
        if self.stopping_new is None:
            return
        generation, since, step = self.stopping_new
        if not generation.running():
            if generation.group_alive():
                generation.signal(signal.SIGKILL)
            self.stopping_new = None
        elif step == 0 and now - since > self.options.stop_seconds:
            generation.signal(signal.SIGKILL)
            self.stopping_new = (generation, now, 1)

    # --- life and death ------------------------------------------------------------------------------------------

    def stop_everything(self, signum):
        if self.watch:
            self.watch.stop.set()
        generations = [g for g in (self.current, self.next, self.old) if g is not None]
        if self.stopping_new:
            generations.append(self.stopping_new[0])
        for generation in generations:
            generation.signal(signum)
        while any(g.running() for g in generations):
            if self.signals:
                # A second signal (systemd's escalation) goes to every generation too.
                number = self.signals.pop(0)
                if number in (signal.SIGTERM, signal.SIGINT):
                    for generation in generations:
                        generation.signal(number)
            time.sleep(0.1)
        return 0

    def run(self):
        self.install()
        self.current = Generation(self.command)
        self.write_state()
        self.say(f'backend started, server pid {self.current.pid}')
        while True:
            while self.signals:
                code = self.take_signal(self.signals.pop(0))
                if code is not None:
                    return code
            if self.current is not None and not self.current.running():
                if self.old is None and self.next is None:
                    return self.current.process.returncode or 1
                if self.next is not None:
                    # The running backend died during a handover: the new one is all there is.
                    self.say('the running backend ended during a handover; the new one carries on')
                    self.old, self.current, self.next = self.current, self.next, None
                    self.old_step = (0, time.monotonic())
                    if self.watch:
                        self.watch.stop.set()
                    self.watch = None
                    self.commit_by = None
                    self.write_state()
            if self.handover is not None:
                self.tick_handover()
            time.sleep(self.options.tick)


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--state', required=True)
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--ready-seconds', type=float, default=300)
    parser.add_argument('--commit-seconds', type=float, default=300)
    parser.add_argument('--stop-seconds', type=float, default=60)
    parser.add_argument('--sigint-seconds', type=float, default=20)
    parser.add_argument('--leftover-seconds', type=float, default=5)
    parser.add_argument('--health-pause', type=float, default=0.2)
    parser.add_argument('--tick', type=float, default=0.1)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if options.command[:1] == ['--']:
        options.command = options.command[1:]
    if not options.command:
        parser.error('no backend command after --')
    if options.workers is None:
        options.workers = 1
        for flag, value in zip(options.command, options.command[1:]):
            if flag == '--workers':
                options.workers = int(value)
    return options


def main(argv=None):
    return Supervisor(parse(sys.argv[1:] if argv is None else argv)).run()


if __name__ == '__main__':
    sys.exit(main())
