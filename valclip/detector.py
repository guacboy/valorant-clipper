"""Detects game events from screen frames by matching HUD cue images.

Cues live in a folder with a cues.json, for example:

    [{"kind": "kill", "image": "kill_banner.png", "roi": [0.4, 0.7, 0.2, 0.25],
      "threshold": 0.8, "cooldown": 0.5, "trigger": "appear"}]

`roi` is x, y, width, height as fractions of the screen. `trigger` is "appear"
(fire when the cue shows up) or "disappear" (fire when it goes away, e.g. an
ability icon going from ready to used). Cue images must be cropped from
footage at the same resolution the game runs at.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from valclip.events import Event, EventKind
from valclip.media import MOTION_SIZE


@dataclass
class Cue:
    kind: EventKind
    image: np.ndarray  # grayscale
    roi: tuple[float, float, float, float]
    threshold: float = 0.8
    cooldown: float = 0.5
    trigger: str = "appear"
    visible: bool = False
    last_fired: float = float("-inf")


def load_cues(folder: Path) -> list[Cue]:
    folder = Path(folder)
    cues = []
    for spec in json.loads((folder / "cues.json").read_text(encoding="utf-8")):
        image = cv2.imread(str(folder / spec["image"]), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"cannot read cue image {folder / spec['image']}")
        if spec.get("trigger", "appear") not in ("appear", "disappear"):
            raise ValueError(f"bad trigger in cue {spec['image']}")
        cues.append(
            Cue(
                kind=EventKind(spec["kind"]),
                image=image,
                roi=tuple(spec["roi"]),
                threshold=float(spec.get("threshold", 0.8)),
                cooldown=float(spec.get("cooldown", 0.5)),
                trigger=spec.get("trigger", "appear"),
            )
        )
    return cues


class MotionMeter:
    """Live camera motion score: mean absolute difference between downscaled frames."""

    def __init__(self) -> None:
        self._previous: np.ndarray | None = None

    def update(self, frame_bgr: np.ndarray) -> float | None:
        small = cv2.cvtColor(cv2.resize(frame_bgr, MOTION_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        previous, self._previous = self._previous, small
        if previous is None:
            return None
        return float(cv2.absdiff(small, previous).mean())


class Detector:
    def __init__(self, cues: list[Cue]) -> None:
        self.cues = cues

    def process(self, frame_bgr: np.ndarray, t: float) -> list[Event]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        fh, fw = gray.shape
        events = []
        for cue in self.cues:
            x, y, w, h = cue.roi
            region = gray[int(y * fh) : int((y + h) * fh), int(x * fw) : int((x + w) * fw)]
            ih, iw = cue.image.shape
            if region.shape[0] < ih or region.shape[1] < iw:
                continue
            score = cv2.matchTemplate(region, cue.image, cv2.TM_CCOEFF_NORMED).max()
            visible = bool(score >= cue.threshold)
            changed = visible != cue.visible
            cue.visible = visible
            fires = visible if cue.trigger == "appear" else not visible
            if changed and fires and t - cue.last_fired >= cue.cooldown:
                cue.last_fired = t
                events.append(Event(cue.kind, t))
        return events
