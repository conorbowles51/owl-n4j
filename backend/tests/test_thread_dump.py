"""SIGUSR1 writes every thread's stack to the process's own file and the process keeps running."""
import pathlib
import signal
import subprocess
import sys
import time

BACKEND = str(pathlib.Path(__file__).resolve().parents[1])


def test_sigusr1_writes_every_threads_stack_to_its_file_and_the_process_carries_on(tmp_path):
    script = ("import sys, threading, time; sys.path.insert(0, sys.argv[1])\n"
              "from services import thread_dump; thread_dump.install()\n"
              "def busy_background_sweep():\n    time.sleep(30)\n"
              "threading.Thread(target=busy_background_sweep, daemon=True).start()\n"
              "print('ready', flush=True); time.sleep(1.5); print('still running', flush=True)")
    env = {'LOUPE_THREAD_DUMP_DIR': str(tmp_path), 'PATH': '/usr/bin:/bin'}
    process = subprocess.Popen([sys.executable, '-c', script, BACKEND], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
    assert process.stdout.readline().strip() == 'ready'
    time.sleep(0.2)
    process.send_signal(signal.SIGUSR1)
    out, err = process.communicate(timeout=20)
    assert 'still running' in out and process.returncode == 0
    dump = (tmp_path / f'threads-{process.pid}.txt').read_text()
    assert 'busy_background_sweep' in dump and dump.count('hread 0x') >= 2
    assert 'busy_background_sweep' not in err
