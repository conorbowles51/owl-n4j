"""Split monolithic data/chat_histories.json into per-chat files + _index.json.

Streams the source file with ijson so memory stays bounded regardless of source size.
Safe to re-run: existing per-chat files are overwritten; the legacy backup is only
created once.
"""

import json
import sys
from pathlib import Path

import ijson

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LEGACY_FILE = DATA_DIR / "chat_histories.json"
LEGACY_BACKUP = DATA_DIR / "chat_histories.json.legacy"
TARGET_DIR = DATA_DIR / "chat_histories"
INDEX_FILE = TARGET_DIR / "_index.json"

SUMMARY_FIELDS = ("id", "name", "timestamp", "created_at", "owner",
                  "snapshot_id", "case_id", "case_version")


def summarize(chat_id: str, chat: dict) -> dict:
    msgs = chat.get("messages") or []
    summary = {k: chat.get(k) for k in SUMMARY_FIELDS}
    summary["id"] = chat.get("id") or chat_id
    summary["message_count"] = len(msgs) if isinstance(msgs, list) else 0
    return summary


def atomic_write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(path)


def main() -> int:
    source = LEGACY_BACKUP if LEGACY_BACKUP.exists() else LEGACY_FILE
    if not source.exists():
        print(f"No source file at {LEGACY_FILE} or {LEGACY_BACKUP}; nothing to migrate.")
        TARGET_DIR.mkdir(parents=True, exist_ok=True)
        if not INDEX_FILE.exists():
            atomic_write_json(INDEX_FILE, {})
        return 0

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    index: dict = {}
    count = 0

    print(f"Streaming {source} ({source.stat().st_size / 1e9:.2f} GB)...")
    with open(source, "rb") as f:
        for chat_id, chat in ijson.kvitems(f, "", use_float=True):
            if not isinstance(chat_id, str) or "/" in chat_id or chat_id.startswith(".."):
                print(f"  skipping unsafe chat_id: {chat_id!r}")
                continue
            if not isinstance(chat, dict):
                print(f"  skipping non-dict chat at {chat_id!r}")
                continue
            atomic_write_json(TARGET_DIR / f"{chat_id}.json", chat)
            index[chat_id] = summarize(chat_id, chat)
            count += 1
            if count % 100 == 0:
                print(f"  migrated {count} chats...")

    atomic_write_json(INDEX_FILE, index)
    print(f"Wrote {count} per-chat files and index to {TARGET_DIR}")

    if source is LEGACY_FILE:
        LEGACY_FILE.rename(LEGACY_BACKUP)
        print(f"Renamed legacy file to {LEGACY_BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
