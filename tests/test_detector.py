import numpy as np

from valclip.detector import Cue, Detector
from valclip.events import EventKind


def make_cue(trigger="appear"):
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, (20, 40), dtype=np.uint8)
    return image, Cue(EventKind.KILL, image, (0.5, 0.5, 0.5, 0.5), threshold=0.9, cooldown=0.5, trigger=trigger)


def frame_with(image=None):
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    if image is not None:
        frame[130:150, 120:160] = image[..., None]
    return frame


def test_fires_once_when_cue_appears():
    image, cue = make_cue()
    det = Detector([cue])
    assert det.process(frame_with(), 0.0) == []
    events = det.process(frame_with(image), 1.0)
    assert [e.kind for e in events] == [EventKind.KILL]
    assert det.process(frame_with(image), 1.1) == []  # still visible: no repeat


def test_cooldown_blocks_flicker():
    image, cue = make_cue()
    det = Detector([cue])
    det.process(frame_with(image), 1.0)
    det.process(frame_with(), 1.1)
    assert det.process(frame_with(image), 1.2) == []
    det.process(frame_with(), 2.0)
    assert len(det.process(frame_with(image), 2.1)) == 1


def test_disappear_trigger():
    image, cue = make_cue("disappear")
    cue.kind = EventKind.ABILITY
    det = Detector([cue])
    assert det.process(frame_with(image), 0.0) == []
    assert [e.kind for e in det.process(frame_with(), 1.0)] == [EventKind.ABILITY]


def test_motion_meter_scores_change():
    from valclip.detector import MotionMeter

    meter = MotionMeter()
    still = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert meter.update(still) is None
    assert meter.update(still) == 0.0
    assert meter.update(np.full_like(still, 200)) > 100
