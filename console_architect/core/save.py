"""Tiny best-score store: ~/.local/share/console-architect/scores.json (never fatal)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _path() -> Path:
    base = os.environ.get("CA_SAVE_DIR") or str(Path.home() / ".local/share/console-architect")
    return Path(base) / "scores.json"


def load_scores() -> dict:
    try:
        return json.loads(_path().read_text())
    except Exception:
        return {}


def record(level_id: str, stars: int, overall: float, retail: float) -> bool:
    """Returns True if this is a new best."""
    try:
        d = load_scores()
        old = d.get(level_id, {})
        best = overall > old.get("overall", -1)
        if best:
            d[level_id] = dict(stars=stars, overall=round(overall, 1), retail=round(retail, 2))
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(d, indent=1))
        return best
    except Exception:
        return False
