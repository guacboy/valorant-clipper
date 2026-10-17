"""FFmpeg helpers: locating the binaries, probing clips and measuring motion."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MOTION_FPS = 4
MOTION_SIZE = (160, 90)


def find_tool(name: str, configured: str | None = None) -> str:
    """Resolves an FFmpeg binary from config, then PATH."""
    if configured:
        return configured
    if found := shutil.which(name):
        return found
    raise FileNotFoundError(f"{name} not found; install FFmpeg or set its path in config.json")


@dataclass(frozen=True)
class ClipInfo:
    duration: float
    has_audio: bool


def probe(clip: Path, ffprobe: str) -> ClipInfo:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(clip)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    data = json.loads(out)
    kinds = {s.get("codec_type") for s in data.get("streams", [])}
    return ClipInfo(float(data["format"]["duration"]), "audio" in kinds)


def motion_scores(clip: Path, ffmpeg: str, start: float, end: float) -> list[tuple[float, float]]:
    """Mean absolute frame difference per sample, as (clip time, score) pairs.

    High values mean fast camera movement (flicks, quick peeks, dashes).
    """
    w, h = MOTION_SIZE
    raw = subprocess.run(
        [
            ffmpeg, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(clip),
            "-vf", f"fps={MOTION_FPS},scale={w}:{h},format=gray", "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    frames = np.frombuffer(raw, dtype=np.uint8)
    frames = frames[: len(frames) // (w * h) * (w * h)].reshape(-1, h, w).astype(np.int16)
    if len(frames) < 2:
        return []
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    return [(start + (i + 1) / MOTION_FPS, float(d)) for i, d in enumerate(diffs)]
