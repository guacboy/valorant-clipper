"""Turns a saved round clip plus its event log into a finished montage."""

import time
from pathlib import Path

from valclip.events import RoundLog
from valclip.media import motion_scores, probe
from valclip.render import build_command, render
from valclip.scoring import select_segments
from valclip.template import Template


def make_montage(
    clip: Path,
    log: RoundLog,
    saved_at: float,
    template: Template,
    output: Path,
    ffmpeg: str,
    ffprobe: str,
    encoder: str,
) -> Path:
    """`saved_at` is the wall clock time the replay ended, used to line events up with clip time."""
    info = probe(clip, ffprobe)
    clip_start = saved_at - info.duration

    lo = max(0.0, log.start - clip_start) if log.start is not None else 0.0
    hi = info.duration  # the replay is saved shortly after the trigger, so it ends there
    if hi - lo < template.duration:
        lo = max(0.0, hi - template.duration)

    events = [(e.kind, e.time - clip_start) for e in log.events]
    if log.motion:
        motion = [(t - clip_start, score) for t, score in log.motion]
    else:
        motion = motion_scores(clip, ffmpeg, lo, hi)  # offline renders have no live samples
    segments = select_segments(events, template.slots, (lo, hi), motion)

    output.parent.mkdir(parents=True, exist_ok=True)
    render(build_command(clip, segments, template, output, ffmpeg, encoder, info.has_audio))
    return output


def montage_path(output_dir: Path) -> Path:
    return Path(output_dir) / f"round_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
