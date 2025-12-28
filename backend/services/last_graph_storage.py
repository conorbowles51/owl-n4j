"""
Last Graph Storage

Stores the Cypher needed to recreate the most recently-cleared graph,
so the user can restore it via the UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from config import BASE_DIR


DATA_DIR = BASE_DIR / "data"
STORAGE_FILE = DATA_DIR / "last_graph.json"


def _ensure_dir() -> None:
  DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_last_graph() -> Optional[Dict]:
  _ensure_dir()
  if not STORAGE_FILE.exists():
    return None
  try:
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
      return json.load(f)
  except (json.JSONDecodeError, OSError):
    return None


def _save_last_graph(data: Dict) -> None:
  _ensure_dir()
  tmp = STORAGE_FILE.with_suffix(".tmp")
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
  tmp.replace(STORAGE_FILE)


class LastGraphStorage:
  """Stores the last-cleared graph's Cypher and metadata."""

  def __init__(self) -> None:
    self._data: Optional[Dict] = _load_last_graph()

  def get(self) -> Optional[Dict]:
    """Get the last stored graph metadata, or None if not present."""
    return self._data

  def set(self, cypher: str) -> Dict:
    """
    Store a new last graph snapshot.

    Args:
      cypher: Cypher string that can recreate the graph.
    """
    record = {
      "cypher": cypher,
      "saved_at": datetime.now().isoformat(),
    }
    self._data = record
    _save_last_graph(record)
    return record


last_graph_storage = LastGraphStorage()






