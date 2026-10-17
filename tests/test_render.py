import json
import subprocess
from pathlib import Path

import pytest

from valclip.events import Event, EventKind, RoundLog
from valclip.media import find_tool, motion_scores, probe
from valclip.pipeline import make_montage
from valclip.render import build_command
from valclip.scoring import Segment
from valclip.template import TemplateError, load_template

try:
    FFMPEG, FFPROBE = find_tool("ffmpeg"), find_tool("ffprobe")
except FileNotFoundError:
    FFMPEG = FFPROBE = None
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")


def write_template(folder: Path, **extra) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    data = {"width": 320, "height": 180, "fps": 30, "slots": [{"duration": 1.0}, {"duration": 1.5}], **extra}
    (folder / "template.json").write_text(json.dumps(data))
    return folder


def test_template_requires_slots(tmp_path):
    (tmp_path / "template.json").write_text(json.dumps({"slots": []}))
    with pytest.raises(TemplateError):
        load_template(tmp_path)


def test_template_missing_asset(tmp_path):
    write_template(tmp_path, overlays=[{"file": "nope.mov"}])
    with pytest.raises(TemplateError):
        load_template(tmp_path)


def test_command_shape(tmp_path):
    template = load_template(write_template(tmp_path))
    cmd = build_command(Path("in.mp4"), [Segment(1, 1.0), Segment(5, 1.5)], template, Path("out.mp4"), "ffmpeg")
    assert cmd.count("-i") == 2
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=1" in graph
    assert cmd[cmd.index("-t", cmd.index("-filter_complex")) + 1] == "2.500"


def test_segment_count_must_match_slots(tmp_path):
    template = load_template(write_template(tmp_path))
    with pytest.raises(ValueError):
        build_command(Path("in.mp4"), [Segment(0, 1.0)], template, Path("out.mp4"), "ffmpeg")


@pytest.fixture
def source_clip(tmp_path) -> Path:
    clip = tmp_path / "round.mp4"
    subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=12",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-shortest",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(clip)],
        check=True,
    )
    return clip


@needs_ffmpeg
def test_end_to_end_render_with_overlay_and_music(tmp_path, source_clip):
    folder = tmp_path / "tpl"
    folder.mkdir()
    subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=red@0.5:size=320x180:rate=30:duration=1",
         "-c:v", "qtrle", str(folder / "flash.mov")],
        check=True,
    )
    subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=5", str(folder / "song.wav")],
        check=True,
    )
    template = load_template(write_template(
        folder,
        overlays=[{"file": "flash.mov", "start": 0.5}],
        music={"file": "song.wav", "offset": 0.5, "volume": 0.5},
    ))
    log = RoundLog(start=1.0, trigger_time=10.0, events=[Event(EventKind.KILL, 4.0), Event(EventKind.DEATH, 10.0)])
    out = make_montage(source_clip, log, 12.0, template, tmp_path / "out.mp4", FFMPEG, FFPROBE, "libx264")
    info = probe(out, FFPROBE)
    assert info.has_audio
    assert info.duration == pytest.approx(template.duration, abs=0.1)


@needs_ffmpeg
def test_motion_scores_cover_range(source_clip):
    scores = motion_scores(source_clip, FFMPEG, 2.0, 6.0)
    assert scores and all(2.0 <= t <= 6.1 for t, _ in scores)


@needs_ffmpeg
def test_live_motion_skips_clip_scan(tmp_path, source_clip, monkeypatch):
    import valclip.pipeline as pipeline

    def no_scan(*_):
        raise AssertionError("clip scan should be skipped when live motion exists")

    monkeypatch.setattr(pipeline, "motion_scores", no_scan)
    template = load_template(write_template(tmp_path / "tpl"))
    log = RoundLog(start=0.0, trigger_time=11.0, motion=[(2.0, 1.0), (8.0, 50.0)])
    out = make_montage(source_clip, log, 12.0, template, tmp_path / "out.mp4", FFMPEG, FFPROBE, "libx264")
    assert out.is_file()
