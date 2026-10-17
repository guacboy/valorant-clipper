"""Montage templates: a list of clip slots plus optional overlays and music.

A template is a folder with a template.json; asset paths inside it are relative
to that folder.
"""

import json
from dataclasses import dataclass
from pathlib import Path


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Overlay:
    file: Path
    start: float


@dataclass(frozen=True)
class Music:
    file: Path
    offset: float  # seconds into the track where the montage begins
    volume: float


@dataclass(frozen=True)
class Template:
    name: str
    width: int
    height: int
    fps: int
    slots: list[float]
    overlays: list[Overlay]
    music: Music | None
    game_volume: float

    @property
    def duration(self) -> float:
        return sum(self.slots)


def _asset(base: Path, name: str) -> Path:
    path = base / name
    if not path.is_file():
        raise TemplateError(f"missing template asset: {path}")
    return path


def load_template(folder: Path) -> Template:
    folder = Path(folder)
    try:
        data = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TemplateError(f"no template.json in {folder}") from exc

    slots = [float(s["duration"]) for s in data.get("slots", [])]
    if not slots or any(d <= 0 for d in slots):
        raise TemplateError("template needs at least one slot, each with a positive duration")

    music = None
    if m := data.get("music"):
        music = Music(_asset(folder, m["file"]), float(m.get("offset", 0.0)), float(m.get("volume", 1.0)))

    return Template(
        name=data.get("name", folder.name),
        width=int(data.get("width", 1920)),
        height=int(data.get("height", 1080)),
        fps=int(data.get("fps", 60)),
        slots=slots,
        overlays=[Overlay(_asset(folder, o["file"]), float(o.get("start", 0.0))) for o in data.get("overlays", [])],
        music=music,
        game_volume=float(data.get("game_volume", 1.0)),
    )
