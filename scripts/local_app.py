"""Run Loupe against isolated synthetic-data services (docker-compose.local.yml)."""

import argparse
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "data" / "local-runtime"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("migrate", "backend", "engine", "worker", "frontend", "setup", "check"))
    parser.add_argument("--case-id", help="Case UUID for read-only check mode")
    args = parser.parse_args()
    if args.case_id and args.service != "check":parser.error("--case-id is only supported with check")
    env = os.environ.copy()
    if os.uname().sysname == "Darwin":
        # Homebrew's PDF libraries are not on macOS's default loader path.
        env.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib:/usr/local/lib")
    # Do not load the real installation's .env or inherit its AI credentials.
    env.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "XDG_CACHE_HOME": str(RUNTIME / "cache"),
        "DATABASE_URL": "postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local",
        "NEO4J_URI": "bolt://127.0.0.1:57687",
        "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": "loupe_local_dev",
        "REDIS_URL": "redis://127.0.0.1:56379",
        "CHROMADB_HOST": "127.0.0.1", "CHROMADB_PORT": "58101",
        "CHROMA_HOST": "127.0.0.1", "CHROMA_PORT": "58101",
        "EVIDENCE_ENGINE_URL": "http://127.0.0.1:58003",
        "EVIDENCE_ENGINE_API_KEY": "loupe-local-service",
        "SERVICE_API_KEY": "loupe-local-service",
        "AUTH_SECRET_KEY": "loupe-local-synthetic-data-only",
        "AI_CREDENTIAL_ENCRYPTION_KEY": "loupe-local-synthetic-data-only",
        "PLATFORM_UPDATE_ENABLED": "false",
        "EVIDENCE_DATA_ROOT": str(RUNTIME / "evidence"),
        "CELLEBRITE_DATA_ROOT": str(RUNTIME / "evidence"),
        "STORAGE_PATH": str(RUNTIME / "files"),
        "TRIAGE_ALLOWED_ROOTS": str(RUNTIME / "evidence"),
        "OPENAI_API_KEY": "local-test-no-api-key",
        "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
        "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "",
        "VIRUSTOTAL_API_KEY": "",
        "CORS_ORIGINS": "http://127.0.0.1:55174,http://localhost:55174",
        "VITE_API_PROXY_TARGET": "http://127.0.0.1:58002",
        "FRONTEND_PORT": "55174",
        "PYTHONPATH": str(ROOT / "backend"),
    })
    for name in ("evidence", "files"):
        (RUNTIME / name).mkdir(parents=True, exist_ok=True)
    python = str(RUNTIME / "backend-venv" / "bin" / "python")
    cwd = ROOT / "backend"
    if args.service in ("setup", "check"):
        command = [python, str(ROOT / "scripts" / "local_verify.py"), args.service]
        if args.case_id:command += ["--case-id", args.case_id]
    elif args.service == "migrate":
        command = [python, "-m", "alembic", "upgrade", "head"]
    elif args.service == "backend":
        command = [python, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "58002"]
    elif args.service in ("engine", "worker"):
        python = str(RUNTIME / "engine-venv" / "bin" / "python")
        env["DATABASE_URL"] = env["DATABASE_URL"].replace("+psycopg", "+asyncpg")
        # A neutral cwd also prevents pydantic-settings loading an engine .env.
        cwd = RUNTIME
        command = ([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "58003"]
                   if args.service == "engine" else [python, "-m", "arq", "app.worker.WorkerSettings"])
    else:
        cwd = ROOT / "frontend_v2"
        command = [str(cwd / "node_modules" / ".bin" / "vite"), "--host", "127.0.0.1", "--strictPort"]
    os.chdir(cwd)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
