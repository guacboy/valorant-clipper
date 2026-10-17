"""Picks which parts of a round clip go into each template slot.

All times in this module are seconds relative to the start of the clip.
"""

from dataclasses import dataclass

from valclip.events import EventKind

WEIGHTS = {
    EventKind.KILL: 10.0,
    EventKind.SPIKE_DEFUSE: 9.0,
    EventKind.SPIKE_PLANT: 7.0,
    EventKind.ABILITY: 4.0,
}
GROUP_GAP = 2.5  # events closer than this merge into one moment (e.g. a multikill)
ANCHOR_RATIO = 0.65  # where the key event lands inside its segment (more lead-up than follow-through)


@dataclass(frozen=True)
class Moment:
    first: float
    last: float
    score: float


@dataclass(frozen=True)
class Segment:
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


def group_moments(events: list[tuple[EventKind, float]]) -> list[Moment]:
    scored = sorted((t, WEIGHTS[k]) for k, t in events if k in WEIGHTS)
    moments: list[Moment] = []
    for t, weight in scored:
        if moments and t - moments[-1].last <= GROUP_GAP:
            prev = moments[-1]
            moments[-1] = Moment(prev.first, t, prev.score + weight)
        else:
            moments.append(Moment(t, t, weight))
    return moments


def _filler_times(
    count: int,
    window: tuple[float, float],
    taken: list[Moment],
    spacing: float,
    motion: list[tuple[float, float]] | None,
) -> list[float]:
    """Times for slots that have no scored moment: highest motion first, else evenly spaced."""
    lo, hi = window
    if motion:
        candidates = [t for t, _ in sorted(motion, key=lambda m: m[1], reverse=True) if lo <= t <= hi]
    else:
        step = (hi - lo) / (count + 1)
        candidates = [lo + step * (i + 1) for i in range(count)]
    picked: list[float] = []
    for t in candidates:
        if len(picked) == count:
            break
        if all(abs(t - m.last) >= spacing for m in taken) and all(abs(t - p) >= spacing for p in picked):
            picked.append(t)
    return picked


def _place(moment: Moment, duration: float, window: tuple[float, float]) -> Segment:
    lo, hi = window
    if moment.last - moment.first + 1.0 > duration:
        start = moment.first - 0.5
    else:
        start = moment.last - duration * ANCHOR_RATIO
    start = min(max(start, lo), max(hi - duration, lo))
    return Segment(start, duration)


def select_segments(
    events: list[tuple[EventKind, float]],
    slot_durations: list[float],
    window: tuple[float, float],
    motion: list[tuple[float, float]] | None = None,
) -> list[Segment]:
    """Returns one segment per slot, in chronological order, within `window`."""
    slots = len(slot_durations)
    lo, hi = window
    moments = [m for m in group_moments(events) if lo <= m.last <= hi]
    best = sorted(moments, key=lambda m: m.score, reverse=True)[:slots]

    missing = slots - len(best)
    if missing:
        spacing = max(slot_durations)
        best += [Moment(t, t, 0.0) for t in _filler_times(missing, window, best, spacing, motion)]
        # The round may be too short to space fillers apart; reuse evenly spaced times then.
        while len(best) < slots:
            t = lo + (hi - lo) * (len(best) + 0.5) / slots
            best.append(Moment(t, t, 0.0))

    best.sort(key=lambda m: m.last)
    segments: list[Segment] = []
    for moment, duration in zip(best, slot_durations):
        seg = _place(moment, duration, window)
        if segments and seg.start < segments[-1].end:
            pushed = segments[-1].end
            if pushed + duration <= hi:
                seg = Segment(pushed, duration)
        segments.append(seg)
    return segments
