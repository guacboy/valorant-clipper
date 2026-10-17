"""Detects game events from screen frames.

Three readers look at the HUD:

- Template cues (cues.json) match fixed images, such as the "PRESS [B] TO BUY"
  line under every buy phase banner.
- KillFeedReader finds your own kill feed entries by their yellow outline:
  on the left portrait when you got the kill, on the right one when you died.
- AbilityMeter watches the charge bars under C, Q, E and the ult dots under X.
  A bar losing charge means you used that ability.

Pixel boxes are measured on 1920x1080 frames and scaled to the real frame size,
so any 16:9 resolution works.

cues.json example:

    [{"kind": "buy_phase", "image": "buy_press.png", "roi": [0.4, 0.2, 0.2, 0.08],
      "threshold": 0.7, "cooldown": 1.0, "trigger": "appear"}]

`roi` is x, y, width, height as fractions of the screen. `trigger` is "appear"
(fire when the cue shows up) or "disappear" (fire when it goes away). Cue images
are grayscale crops from 1920x1080 footage.
"""

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from valclip.events import Event, EventKind
from valclip.media import MOTION_SIZE

REF_W, REF_H = 1920, 1080


def _crop(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Crops a (x0, y0, x1, y1) box given in 1920x1080 pixels."""
    fh, fw = frame.shape[:2]
    x0, y0, x1, y1 = box
    return frame[y0 * fh // REF_H : y1 * fh // REF_H, x0 * fw // REF_W : x1 * fw // REF_W]


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


class Reader(Protocol):
    def update(self, frame_bgr: np.ndarray, t: float) -> list[Event]: ...


class KillFeedReader:
    FEED_BOX = (1450, 80, 1910, 430)
    VICTIM_X = 1830  # outlines starting right of this are on the victim portrait
    MIN_RUN = 30  # shortest horizontal yellow run that counts as an outline edge
    EDGE_GAP = (28, 38)  # distance between the top and bottom edge of one outline
    EDGE_SHIFT = 8  # the two edges of one outline start at nearly the same x
    ENTRY_SPAN = 36  # outlines closer than this belong to the same entry
    YELLOW = ((22, 110, 150), (36, 255, 255))  # HSV range of the outline
    SETTLE = 3  # frames a lower count must persist before it is accepted

    def __init__(self) -> None:
        self._counts = (0, 0)
        self._low_frames = 0

    def read(self, frame_bgr: np.ndarray) -> tuple[int, int]:
        """Returns (your kills, your deaths) currently visible in the kill feed."""
        roi = _crop(frame_bgr, self.FEED_BOX)
        scale = roi.shape[1] / (self.FEED_BOX[2] - self.FEED_BOX[0])
        mask = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), *self.YELLOW) > 0
        runs = []  # (y, x) of every horizontal yellow edge, in 1080p units
        for y, row in enumerate(mask):
            start, length = _longest_run(row)
            if length >= self.MIN_RUN * scale:
                runs.append((y / scale, self.FEED_BOX[0] + start / scale))
        # A real outline has a matching bottom edge; stray yellow (skins, clothing) does not.
        lo, hi = self.EDGE_GAP
        tops: dict[bool, list[float]] = {True: [], False: []}  # victim side -> outline tops
        for y, x in runs:
            if any(lo <= y2 - y <= hi and abs(x2 - x) <= self.EDGE_SHIFT for y2, x2 in runs):
                tops[x >= self.VICTIM_X].append(y)
        return _count_clusters(tops[False], self.ENTRY_SPAN), _count_clusters(tops[True], self.ENTRY_SPAN)

    def update(self, frame_bgr: np.ndarray, t: float) -> list[Event]:
        counts = self.read(frame_bgr)
        events = []
        for kind, now, before in zip((EventKind.KILL, EventKind.DEATH), counts, self._counts):
            events += [Event(kind, t)] * max(0, now - before)
        if any(n < b for n, b in zip(counts, self._counts)):
            self._low_frames += 1
            if self._low_frames < self.SETTLE:
                counts = tuple(max(n, b) for n, b in zip(counts, self._counts))
        else:
            self._low_frames = 0
        self._counts = counts
        return events


def _longest_run(row: np.ndarray) -> tuple[int, int]:
    padded = np.concatenate(([False], row, [False])).astype(np.int8)
    changes = np.flatnonzero(np.diff(padded))
    if len(changes) == 0:
        return 0, 0
    starts, ends = changes[::2], changes[1::2]
    i = int(np.argmax(ends - starts))
    return int(starts[i]), int(ends[i] - starts[i])


def _count_clusters(rows: list[float], span: float) -> int:
    count, first = 0, None
    for y in rows:
        if first is None or y - first > span:
            count += 1
            first = y
    return count


class AbilityMeter:
    SLOTS = {
        "C": (745, 1036, 835, 1054),
        "Q": (857, 1036, 945, 1054),
        "E": (970, 1036, 1057, 1054),
        "X": (1095, 1026, 1165, 1038),
    }
    TEAL = ((70, 90, 130), (95, 255, 255))  # HSV range of a filled charge
    DROP = 0.08  # fraction of a bar that must empty to count as a use
    HIDDEN = 0.02  # every slot below this means the HUD is covered (buy menu, map)
    SMOOTH = 3  # frames in the median filter

    def __init__(self) -> None:
        self._history: deque[np.ndarray] = deque(maxlen=self.SMOOTH)
        self._levels: np.ndarray | None = None

    def read(self, frame_bgr: np.ndarray) -> np.ndarray:
        levels = []
        for box in self.SLOTS.values():
            hsv = cv2.cvtColor(_crop(frame_bgr, box), cv2.COLOR_BGR2HSV)
            levels.append(float(np.mean(cv2.inRange(hsv, *self.TEAL) > 0)))
        return np.array(levels)

    def update(self, frame_bgr: np.ndarray, t: float) -> list[Event]:
        levels = self.read(frame_bgr)
        if levels.max() < self.HIDDEN:
            self._history.clear()
            return []
        self._history.append(levels)
        if len(self._history) < self.SMOOTH:
            return []
        current = np.median(np.array(self._history), axis=0)
        if self._levels is None:
            self._levels = current
            return []
        drops = np.flatnonzero(self._levels - current >= self.DROP)
        if len(drops) > 1:
            # Several slots changing at once means the HUD changed (spectating, new round), not a cast.
            self._levels = current
            return []
        rises = current - self._levels >= self.DROP
        self._levels = np.where(rises, current, self._levels)
        if len(drops) == 1:
            self._levels[drops[0]] = current[drops[0]]
            return [Event(EventKind.ABILITY, t)]
        return []


class Detector:
    def __init__(self, cues: list[Cue], readers: list[Reader] | None = None) -> None:
        self.cues = cues
        self.readers = readers or []

    def process(self, frame_bgr: np.ndarray, t: float) -> list[Event]:
        events = self._match_cues(frame_bgr, t)
        for reader in self.readers:
            events += reader.update(frame_bgr, t)
        return events

    def _match_cues(self, frame_bgr: np.ndarray, t: float) -> list[Event]:
        if not self.cues:
            return []
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        fh, fw = gray.shape
        events = []
        for cue in self.cues:
            x, y, w, h = cue.roi
            region = gray[int(y * fh) : int((y + h) * fh), int(x * fw) : int((x + w) * fw)]
            image = cue.image if fw == REF_W else cv2.resize(cue.image, None, fx=fw / REF_W, fy=fh / REF_H)
            ih, iw = image.shape
            if region.shape[0] < ih or region.shape[1] < iw:
                continue
            score = cv2.matchTemplate(region, image, cv2.TM_CCOEFF_NORMED).max()
            visible = bool(score >= cue.threshold)
            changed = visible != cue.visible
            cue.visible = visible
            fires = visible if cue.trigger == "appear" else not visible
            if changed and fires and t - cue.last_fired >= cue.cooldown:
                cue.last_fired = t
                events.append(Event(cue.kind, t))
        return events
