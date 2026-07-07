"""Admin-triggered platform update status and launcher service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from threading import RLock
from typing import Callable, Sequence

from config import (
    PLATFORM_UPDATE_BRANCH,
    PLATFORM_UPDATE_ENABLED,
    PLATFORM_UPDATE_POLL_SECONDS,
    PLATFORM_UPDATE_REMOTE,
    PLATFORM_UPDATE_REPO_DIR,
    PLATFORM_UPDATE_SERVICE,
)
from services.system_log_service import LogOrigin, LogType, system_log_service


Runner = Callable[[Sequence[str], Path | None, int], subprocess.CompletedProcess[str]]

SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+\.service$")
LOG_TAIL_BYTES = 40_000


class PlatformUpdateError(Exception):
    """Raised when a platform update action cannot be performed."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _short_sha(value: str | None) -> str | None:
    return value[:8] if value else None


def _normalize_branch(value: str | None) -> str | None:
    if not value:
        return None
    branch = value.strip()
    if branch.startswith("refs/heads/"):
        return branch.removeprefix("refs/heads/")
    if branch.startswith("origin/"):
        return branch.removeprefix("origin/")
    return branch or None


def _default_runner(
    command: Sequence[str],
    cwd: Path | None,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class PlatformUpdateService:
    """Checks remote git state and safely starts a fixed systemd deploy unit."""

    def __init__(
        self,
        *,
        enabled: bool,
        repo_dir: Path,
        remote: str = "origin",
        branch: str | None = None,
        poll_seconds: int = 3600,
        service_name: str = "owl-self-update.service",
        runner: Runner = _default_runner,
        logger=system_log_service,
    ) -> None:
        self.enabled = enabled
        self.repo_dir = Path(repo_dir)
        self.remote = remote
        self.branch = _normalize_branch(branch)
        self.poll_seconds = max(60, poll_seconds)
        self.service_name = service_name
        self._runner = runner
        self._logger = logger
        self._lock = RLock()
        self._state: dict[str, object] = self._base_state()
        self._last_deploy_requested_by: str | None = None
        self._last_deploy_started_at: datetime | None = None
        self._last_deploy_error: str | None = None

    def _base_state(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "configured": False,
            "config_error": None,
            "can_deploy": False,
            "repo_dir": str(self.repo_dir),
            "remote": self.remote,
            "branch": self.branch,
            "service_name": self.service_name,
            "local_sha": None,
            "local_short_sha": None,
            "remote_sha": None,
            "remote_short_sha": None,
            "update_available": False,
            "last_checked_at": None,
            "last_check_error": None,
            "deployment_running": False,
            "deployment_status": "idle",
            "deployment_error": None,
            "deployment_started_at": None,
            "deployment_completed_at": None,
            "last_deploy_requested_by": None,
            "deploy_log_path": None,
            "deploy_log_tail": None,
        }

    def _run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = 15,
    ) -> subprocess.CompletedProcess[str]:
        return self._runner(command, cwd, timeout)

    def _run_git(self, args: Sequence[str], timeout: int = 15) -> str:
        result = self._run(["git", *args], cwd=self.repo_dir, timeout=timeout)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "git command failed").strip()
            raise PlatformUpdateError(message, status_code=502)
        return (result.stdout or "").strip()

    def _resolve_branch(self) -> str | None:
        if self.branch:
            return self.branch
        try:
            branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        except PlatformUpdateError:
            return None
        return _normalize_branch(branch if branch != "HEAD" else None)

    @staticmethod
    def _parse_systemctl_show(output: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in output.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _get_service_state(self) -> tuple[dict[str, object], str | None]:
        if not SERVICE_NAME_RE.match(self.service_name):
            return {"configured": False, "deployment_status": "unknown"}, "Invalid update service name"

        command = [
            "sudo",
            "-n",
            "systemctl",
            "show",
            self.service_name,
            "--property=LoadState,ActiveState,SubState,Result,ExecMainStartTimestamp,ExecMainExitTimestamp",
            "--no-pager",
        ]
        try:
            result = self._run(command, cwd=None, timeout=8)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"configured": False, "deployment_status": "unknown"}, str(exc)

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Unable to inspect update service").strip()
            return {"configured": False, "deployment_status": "unknown"}, message

        values = self._parse_systemctl_show(result.stdout or "")
        load_state = values.get("LoadState")
        active_state = values.get("ActiveState")
        sub_state = values.get("SubState")
        result_state = values.get("Result")
        running = active_state in {"activating", "active"} or sub_state == "running"

        if running:
            deployment_status = "running"
        elif result_state and result_state != "success":
            deployment_status = "failed"
        elif result_state == "success" and self._last_deploy_started_at:
            deployment_status = "succeeded"
        else:
            deployment_status = "idle"

        return (
            {
                "configured": load_state == "loaded",
                "deployment_running": running,
                "deployment_status": deployment_status,
                "deployment_started_at": values.get("ExecMainStartTimestamp") or _iso(self._last_deploy_started_at),
                "deployment_completed_at": values.get("ExecMainExitTimestamp") or None,
            },
            None if load_state == "loaded" else f"Service {self.service_name} is not loaded",
        )

    def _latest_deploy_log(self) -> tuple[str | None, str | None]:
        log_dir = self.repo_dir / "deploy" / "logs"
        try:
            latest = max(log_dir.glob("deploy-*.log"), key=lambda path: path.stat().st_mtime)
        except ValueError:
            return None, None
        except OSError as exc:
            return None, f"Unable to read deploy logs: {exc}"

        try:
            size = latest.stat().st_size
            with latest.open("rb") as handle:
                if size > LOG_TAIL_BYTES:
                    handle.seek(-LOG_TAIL_BYTES, 2)
                data = handle.read().decode("utf-8", errors="replace")
        except OSError as exc:
            return str(latest), f"Unable to read deploy log: {exc}"

        return str(latest), data

    def refresh_status(self) -> dict[str, object]:
        """Refresh git, service, and log state."""
        now = _utc_now()
        next_state = self._base_state()
        next_state["last_checked_at"] = _iso(now)

        if not self.enabled:
            next_state["last_check_error"] = "Platform updates are disabled"
            with self._lock:
                self._state = next_state
                return dict(self._state)

        if not self.repo_dir.exists():
            next_state["config_error"] = f"Repository directory does not exist: {self.repo_dir}"
            next_state["last_check_error"] = next_state["config_error"]
            with self._lock:
                self._state = next_state
                return dict(self._state)

        service_state, service_error = self._get_service_state()
        next_state.update(service_state)
        next_state["config_error"] = service_error

        try:
            branch = self._resolve_branch()
            next_state["branch"] = branch
            if not branch:
                raise PlatformUpdateError("Unable to determine update branch", status_code=500)

            local_sha = self._run_git(["rev-parse", "HEAD"])
            remote_output = self._run_git(["ls-remote", self.remote, branch], timeout=20)
            remote_sha = remote_output.split()[0] if remote_output.split() else None
            if not remote_sha:
                raise PlatformUpdateError(f"No remote SHA found for {self.remote}/{branch}", status_code=502)

            next_state["local_sha"] = local_sha
            next_state["local_short_sha"] = _short_sha(local_sha)
            next_state["remote_sha"] = remote_sha
            next_state["remote_short_sha"] = _short_sha(remote_sha)
            next_state["update_available"] = local_sha != remote_sha
            next_state["last_check_error"] = service_error
        except PlatformUpdateError as exc:
            next_state["last_check_error"] = str(exc)
        except Exception as exc:
            next_state["last_check_error"] = str(exc)

        log_path, log_tail = self._latest_deploy_log()
        next_state["deploy_log_path"] = log_path
        next_state["deploy_log_tail"] = log_tail
        next_state["deployment_error"] = self._last_deploy_error
        next_state["last_deploy_requested_by"] = self._last_deploy_requested_by
        next_state["can_deploy"] = bool(
            next_state["enabled"]
            and next_state["configured"]
            and next_state["update_available"]
            and not next_state["deployment_running"]
            and not next_state["last_check_error"]
        )

        with self._lock:
            self._state = next_state
            return dict(self._state)

    def get_status(self) -> dict[str, object]:
        """Return cached state with fresh systemd/log information when enabled."""
        if self.enabled:
            with self._lock:
                state = dict(self._state)
            service_state, service_error = self._get_service_state()
            log_path, log_tail = self._latest_deploy_log()
            state.update(service_state)
            state["config_error"] = service_error
            state["deploy_log_path"] = log_path
            state["deploy_log_tail"] = log_tail
            state["deployment_error"] = self._last_deploy_error
            state["last_deploy_requested_by"] = self._last_deploy_requested_by
            state["can_deploy"] = bool(
                state["enabled"]
                and state["configured"]
                and state["update_available"]
                and not state["deployment_running"]
                and not state["last_check_error"]
            )
            with self._lock:
                self._state = state
                return dict(state)

        with self._lock:
            return dict(self._state)

    def trigger_deploy(self, *, requested_by: str | None) -> dict[str, object]:
        """Start the fixed self-update systemd unit."""
        status = self.refresh_status()
        if not status["enabled"]:
            raise PlatformUpdateError("Platform updates are disabled", status_code=409)
        if not status["configured"]:
            raise PlatformUpdateError(status.get("config_error") or "Update service is not configured", status_code=409)
        if status["deployment_running"]:
            raise PlatformUpdateError("A platform update is already running", status_code=409)
        if not status["update_available"]:
            raise PlatformUpdateError("No platform update is available", status_code=409)

        command = ["sudo", "-n", "systemctl", "start", "--no-block", self.service_name]
        self._last_deploy_requested_by = requested_by
        self._last_deploy_started_at = _utc_now()
        self._last_deploy_error = None

        self._log(
            "Platform update requested",
            user=requested_by,
            success=True,
            details={
                "service": self.service_name,
                "branch": status.get("branch"),
                "local_sha": status.get("local_sha"),
                "remote_sha": status.get("remote_sha"),
            },
        )

        result = self._run(command, cwd=None, timeout=15)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Failed to start update service").strip()
            self._last_deploy_error = message
            self._log(
                "Platform update start failed",
                user=requested_by,
                success=False,
                error=message,
                details={"service": self.service_name},
            )
            raise PlatformUpdateError(message, status_code=500)

        self._log(
            "Platform update service started",
            user=requested_by,
            success=True,
            details={"service": self.service_name},
        )
        return self.get_status()

    async def poll_forever(self) -> None:
        """Periodically refresh update availability."""
        if not self.enabled:
            return
        while True:
            try:
                await asyncio.to_thread(self.refresh_status)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log(
                    "Platform update poll failed",
                    success=False,
                    error=str(exc),
                    details={"service": self.service_name},
                )
            await asyncio.sleep(self.poll_seconds)

    def _log(
        self,
        action: str,
        *,
        user: str | None = None,
        success: bool = True,
        error: str | None = None,
        details: dict | None = None,
    ) -> None:
        if not self._logger:
            return
        self._logger.log(
            LogType.SYSTEM,
            LogOrigin.BACKEND,
            action,
            details=details or {},
            user=user,
            success=success,
            error=error,
        )


platform_update_service = PlatformUpdateService(
    enabled=PLATFORM_UPDATE_ENABLED,
    repo_dir=PLATFORM_UPDATE_REPO_DIR,
    remote=PLATFORM_UPDATE_REMOTE,
    branch=PLATFORM_UPDATE_BRANCH,
    poll_seconds=PLATFORM_UPDATE_POLL_SECONDS,
    service_name=PLATFORM_UPDATE_SERVICE,
)
