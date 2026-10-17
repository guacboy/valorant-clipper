from dataclasses import dataclass, field
from enum import Enum


class EventKind(str, Enum):
    ROUND_START = "round_start"
    ROUND_END = "round_end"
    KILL = "kill"
    DEATH = "death"
    ABILITY = "ability"
    SPIKE_PLANT = "spike_plant"
    SPIKE_DEFUSE = "spike_defuse"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    time: float  # wall clock seconds, as returned by time.time()


@dataclass
class RoundLog:
    start: float | None  # None when the app started mid-round
    trigger_time: float
    events: list[Event] = field(default_factory=list)
    motion: list[tuple[float, float]] = field(default_factory=list)  # (wall time, score)


class RoundTracker:
    """Collects events for the current round and decides when to make a montage.

    The montage is triggered by the player's death, or by the round end when the
    player survived. Events after the trigger are ignored until the next round.
    """

    def __init__(self) -> None:
        self._reset(None)

    def _reset(self, start: float | None) -> None:
        self._start = start
        self._events: list[Event] = []
        self._motion: list[tuple[float, float]] = []
        self._triggered = False

    def add_motion(self, t: float, score: float) -> None:
        if not self._triggered:
            self._motion.append((t, score))

    def feed(self, event: Event) -> RoundLog | None:
        if event.kind is EventKind.ROUND_START:
            self._reset(event.time)
            return None
        if self._triggered:
            return None
        if event.kind in (EventKind.DEATH, EventKind.ROUND_END):
            self._triggered = True
            if event.kind is EventKind.DEATH:
                self._events.append(event)
            return RoundLog(self._start, event.time, list(self._events), list(self._motion))
        self._events.append(event)
        return None
