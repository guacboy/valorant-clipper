"""Keeps saved replays and finished montages for the current game only."""

import shutil
import time
from pathlib import Path

# Only files with these prefixes are ever deleted, so anything else in the folders is safe.
REPLAY_PREFIX = "replay_"
MONTAGE_PREFIX = "round_"


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def store_replay(saved: Path, folder: Path) -> Path:
    """Moves a replay OBS just saved into `folder` under a name the cleanup recognizes."""
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(saved, folder / f"{REPLAY_PREFIX}{_stamp()}{saved.suffix}"))


def montage_path(folder: Path) -> Path:
    return folder / f"{MONTAGE_PREFIX}{_stamp()}.mp4"


def _clear(folder: Path, prefix: str) -> int:
    removed = 0
    for path in folder.glob(f"{prefix}*"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def clear_game(replay_dir: Path, output_dir: Path) -> tuple[int, int]:
    """Deletes the previous game's replays and montages; returns how many of each."""
    return _clear(replay_dir, REPLAY_PREFIX), _clear(output_dir, MONTAGE_PREFIX)
