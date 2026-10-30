"""SIGUSR1 writes every thread's stack to the process's own file and the process keeps running."""
import os
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


def test_a_dump_while_other_threads_run_python_code_does_not_crash(tmp_path):
    """faulthandler's dump of running threads crashed a live process (SIGSEGV, 2026-10-30 15:36)."""
    script = (
        "import os, signal, sys, threading, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from services import thread_dump\n"
        "thread_dump.install()\n"
        "def busy():\n"
        "    while True:\n"
        "        sorted(str(i) for i in range(2000))\n"
        "for _ in range(4):\n"
        "    threading.Thread(target=busy, name='busy_worker', daemon=True).start()\n"
        "for _ in range(200):\n"
        "    os.kill(os.getpid(), signal.SIGUSR1)\n"
        "    time.sleep(0.005)\n"
        "print('alive')\n"
    )
    env = {**os.environ, 'LOUPE_THREAD_DUMP_DIR': str(tmp_path)}
    done = subprocess.run([sys.executable, '-c', script, BACKEND], env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and 'alive' in done.stdout, done.stderr[-2000:]
    text = next(tmp_path.glob('threads-*.txt')).read_text()
    assert 'busy_worker' in text and 'in busy' in text


def test_the_dump_is_not_taken_by_faulthandler():
    """faulthandler reads running threads' frames from the C signal handler (documented unsafe); live 2026-10-30
    15:36 a process ended with SIGSEGV half-way through such a dump. A stress run does not reproduce it reliably,
    so the mechanism itself is checked."""
    script = ("import faulthandler, signal, sys; sys.path.insert(0, sys.argv[1])\n"
              "from services import thread_dump; thread_dump.install()\n"
              "print(faulthandler.unregister(signal.SIGUSR1), callable(signal.getsignal(signal.SIGUSR1)))")
    done = subprocess.run([sys.executable, '-c', script, BACKEND], capture_output=True, text=True, timeout=60,
                          env={**os.environ, 'LOUPE_THREAD_DUMP_DIR': '/tmp/loupe-thread-dumps-test-' + str(os.getuid())})
    assert done.stdout.split() == ['False', 'True'], done.stderr[-2000:]
