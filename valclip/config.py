import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    capture_monitor: int = 0  # dxcam output index of the monitor Valorant runs on
    viewer_monitor: int = 1  # Qt screen index where montages pop up
    detect_fps: int = 10
    post_roll: float = 1.5  # seconds kept after the trigger before saving the replay
    cues_dir: str = "assets/cues"
    template_dir: str = "templates/default"
    output_dir: str = "output"
    encoder: str = "h264_nvenc"
    ffmpeg: str | None = None
    ffprobe: str | None = None


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.is_file():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    return Config(**data)
