"""Builds and runs the FFmpeg command that fills a template with clip segments."""

import subprocess
from pathlib import Path

from valclip.scoring import Segment
from valclip.template import Template

ENCODER_ARGS = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21"],
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"],
}


class RenderError(RuntimeError):
    pass


def build_command(
    source: Path,
    segments: list[Segment],
    template: Template,
    output: Path,
    ffmpeg: str,
    encoder: str = "h264_nvenc",
    has_audio: bool = True,
) -> list[str]:
    if len(segments) != len(template.slots):
        raise ValueError(f"expected {len(template.slots)} segments, got {len(segments)}")
    if encoder not in ENCODER_ARGS:
        raise ValueError(f"unknown encoder {encoder!r}; use one of {sorted(ENCODER_ARGS)}")

    w, h, fps = template.width, template.height, template.fps
    args = [ffmpeg, "-y", "-v", "error"]
    graph: list[str] = []

    for i, seg in enumerate(segments):
        args += ["-ss", f"{seg.start:.3f}", "-t", f"{seg.duration:.3f}", "-i", str(source)]
        graph.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
        )
        if has_audio:
            graph.append(f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]")
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={seg.duration:.3f}[a{i}]")

    pairs = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    graph.append(f"{pairs}concat=n={len(segments)}:v=1:a=1[base][game]")

    video = "base"
    index = len(segments)
    for n, overlay in enumerate(template.overlays):
        args += ["-i", str(overlay.file)]
        graph.append(f"[{index}:v]scale={w}:{h},setpts=PTS-STARTPTS+{overlay.start:.3f}/TB[o{n}]")
        graph.append(f"[{video}][o{n}]overlay=eof_action=pass[ov{n}]")
        video = f"ov{n}"
        index += 1
    graph.append(f"[{video}]format=yuv420p[vout]")

    graph.append(f"[game]volume={template.game_volume}[gamevol]")
    if template.music:
        args += ["-i", str(template.music.file)]
        graph.append(
            f"[{index}:a]atrim=start={template.music.offset:.3f},asetpts=PTS-STARTPTS,"
            f"volume={template.music.volume}[music]"
        )
        graph.append("[gamevol][music]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        graph.append("[gamevol]anull[aout]")

    args += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]"]
    args += ENCODER_ARGS[encoder]
    args += ["-c:a", "aac", "-b:a", "192k", "-t", f"{template.duration:.3f}", "-movflags", "+faststart", str(output)]
    return args


def render(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(f"ffmpeg failed ({result.returncode}): {result.stderr.strip()[-2000:]}")
