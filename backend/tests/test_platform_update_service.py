import subprocess
import tempfile
import unittest
from pathlib import Path

from services.platform_update_service import PlatformUpdateError, PlatformUpdateService


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class FakeRunner:
    def __init__(self, responses):
        self.responses = {tuple(key): value for key, value in responses.items()}
        self.commands = []

    def __call__(self, command, cwd, timeout):
        key = tuple(command)
        self.commands.append((key, cwd, timeout))
        response = self.responses.get(key)
        if response is None:
            raise AssertionError(f"Unexpected command: {key}")
        return response


class PlatformUpdateServiceTests(unittest.TestCase):
    def test_disabled_status_is_safe_and_does_not_shell_out(self):
        runner = FakeRunner({})
        service = PlatformUpdateService(
            enabled=False,
            repo_dir=Path("/missing"),
            runner=runner,
            logger=None,
        )

        status = service.refresh_status()

        self.assertFalse(status["enabled"])
        self.assertFalse(status["configured"])
        self.assertFalse(status["can_deploy"])
        self.assertEqual(status["last_check_error"], "Platform updates are disabled")
        self.assertEqual(runner.commands, [])

    def test_detects_update_available_from_normalized_git_state(self):
        repo_dir = Path.cwd()
        runner = FakeRunner(
            {
                ("sudo", "-n", "systemctl", "show", "owl-self-update.service", "--property=LoadState,ActiveState,SubState,Result,ExecMainStartTimestamp,ExecMainExitTimestamp", "--no-pager"): completed(
                    ["systemctl"],
                    stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nResult=success\n",
                ),
                ("git", "rev-parse", "HEAD"): completed(["git"], stdout="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"),
                ("git", "ls-remote", "origin", "main"): completed(
                    ["git"],
                    stdout="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/heads/main\n",
                ),
            }
        )
        service = PlatformUpdateService(
            enabled=True,
            repo_dir=repo_dir,
            branch="origin/main",
            runner=runner,
            logger=None,
        )

        status = service.refresh_status()

        self.assertTrue(status["configured"])
        self.assertEqual(status["branch"], "main")
        self.assertEqual(status["local_short_sha"], "aaaaaaaa")
        self.assertEqual(status["remote_short_sha"], "bbbbbbbb")
        self.assertTrue(status["update_available"])
        self.assertTrue(status["can_deploy"])

    def test_missing_systemd_unit_is_not_configured(self):
        repo_dir = Path.cwd()
        runner = FakeRunner(
            {
                ("sudo", "-n", "systemctl", "show", "owl-self-update.service", "--property=LoadState,ActiveState,SubState,Result,ExecMainStartTimestamp,ExecMainExitTimestamp", "--no-pager"): completed(
                    ["systemctl"],
                    stdout="LoadState=not-found\nActiveState=inactive\nSubState=dead\nResult=success\n",
                ),
                ("git", "rev-parse", "HEAD"): completed(["git"], stdout="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"),
                ("git", "ls-remote", "origin", "main"): completed(
                    ["git"],
                    stdout="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/heads/main\n",
                ),
            }
        )
        service = PlatformUpdateService(
            enabled=True,
            repo_dir=repo_dir,
            branch="main",
            runner=runner,
            logger=None,
        )

        status = service.refresh_status()

        self.assertFalse(status["configured"])
        self.assertFalse(status["can_deploy"])
        self.assertIn("not loaded", status["config_error"])

    def test_deploy_runs_only_fixed_systemd_start_command(self):
        repo_dir = Path.cwd()
        show_command = (
            "sudo",
            "-n",
            "systemctl",
            "show",
            "owl-self-update.service",
            "--property=LoadState,ActiveState,SubState,Result,ExecMainStartTimestamp,ExecMainExitTimestamp",
            "--no-pager",
        )
        runner = FakeRunner(
            {
                show_command: completed(
                    ["systemctl"],
                    stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nResult=success\n",
                ),
                ("git", "rev-parse", "HEAD"): completed(["git"], stdout="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"),
                ("git", "ls-remote", "origin", "main"): completed(
                    ["git"],
                    stdout="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/heads/main\n",
                ),
                ("sudo", "-n", "systemctl", "start", "--no-block", "owl-self-update.service"): completed(
                    ["systemctl"],
                    stdout="",
                ),
            }
        )
        service = PlatformUpdateService(
            enabled=True,
            repo_dir=repo_dir,
            branch="main",
            runner=runner,
            logger=None,
        )

        service.trigger_deploy(requested_by="admin@example.com")

        commands = [command for command, _cwd, _timeout in runner.commands]
        self.assertIn(
            ("sudo", "-n", "systemctl", "start", "--no-block", "owl-self-update.service"),
            commands,
        )

    def test_deploy_rejects_when_no_update_is_available(self):
        repo_dir = Path.cwd()
        runner = FakeRunner(
            {
                ("sudo", "-n", "systemctl", "show", "owl-self-update.service", "--property=LoadState,ActiveState,SubState,Result,ExecMainStartTimestamp,ExecMainExitTimestamp", "--no-pager"): completed(
                    ["systemctl"],
                    stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nResult=success\n",
                ),
                ("git", "rev-parse", "HEAD"): completed(["git"], stdout="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"),
                ("git", "ls-remote", "origin", "main"): completed(
                    ["git"],
                    stdout="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/heads/main\n",
                ),
            }
        )
        service = PlatformUpdateService(
            enabled=True,
            repo_dir=repo_dir,
            branch="main",
            runner=runner,
            logger=None,
        )

        with self.assertRaises(PlatformUpdateError) as ctx:
            service.trigger_deploy(requested_by="admin@example.com")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("No platform update", str(ctx.exception))

    def test_deploy_log_tail_is_capped_to_recent_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir)
            log_dir = repo_dir / "deploy" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "deploy-20990101-000000.log"
            log_path.write_text("\n".join(f"line {i}" for i in range(7000)), encoding="utf-8")
            runner = FakeRunner({})
            service = PlatformUpdateService(
                enabled=False,
                repo_dir=repo_dir,
                runner=runner,
                logger=None,
            )

            path, tail = service._latest_deploy_log()

            self.assertEqual(path, str(log_path))
            self.assertIn("line 6999", tail)
            self.assertNotIn("line 0", tail)


if __name__ == "__main__":
    unittest.main()
