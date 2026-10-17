import numpy as np

from valclip.detector import Cue, Detector
from valclip.events import EventKind


def make_cue(trigger="appear"):
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, (20, 40), dtype=np.uint8)
    return image, Cue(EventKind.KILL, image, (0.5, 0.5, 0.5, 0.5), threshold=0.9, cooldown=0.5, trigger=trigger)


def frame_with(image=None):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    if image is not None:
        frame[700:720, 1200:1240] = image[..., None]
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


def hsv_bgr(h, s, v):
    import cv2

    return tuple(int(c) for c in cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0])


YELLOW = hsv_bgr(30, 200, 230)
TEAL = hsv_bgr(82, 180, 200)


def feed_frame(kills=0, died=False):
    import cv2

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for i in range(kills):
        top = 100 + 39 * i
        cv2.rectangle(frame, (1570, top), (1640, top + 33), YELLOW, 2)
    if died:
        cv2.rectangle(frame, (1861, 300), (1899, 333), YELLOW, 2)
    return frame


def test_kill_feed_counts_own_entries():
    from valclip.detector import KillFeedReader

    assert KillFeedReader().read(feed_frame(kills=2, died=True)) == (2, 1)
    assert KillFeedReader().read(feed_frame()) == (0, 0)


def test_kill_feed_emits_new_kills_and_death():
    from valclip.detector import KillFeedReader

    reader = KillFeedReader()
    assert [e.kind for e in reader.update(feed_frame(kills=1), 1.0)] == [EventKind.KILL]
    assert reader.update(feed_frame(kills=1), 1.1) == []
    kinds = [e.kind for e in reader.update(feed_frame(kills=2, died=True), 1.2)]
    assert kinds == [EventKind.KILL, EventKind.DEATH]


def test_kill_feed_ignores_one_frame_dropout():
    from valclip.detector import KillFeedReader

    reader = KillFeedReader()
    reader.update(feed_frame(kills=1), 1.0)
    reader.update(feed_frame(), 1.1)  # e.g. a flash washes the feed out
    assert reader.update(feed_frame(kills=1), 1.2) == []


def test_kill_feed_scales_to_other_resolutions():
    import cv2

    from valclip.detector import KillFeedReader

    small = cv2.resize(feed_frame(kills=1, died=True), (1280, 720), interpolation=cv2.INTER_NEAREST)
    assert KillFeedReader().read(small) == (1, 1)


def ability_frame(**filled):
    import cv2

    from valclip.detector import AbilityMeter

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for slot, (x0, y0, x1, y1) in AbilityMeter.SLOTS.items():
        width = int((x1 - x0) * filled.get(slot, 0.0))
        if width:
            cv2.rectangle(frame, (x0, y0), (x0 + width - 1, y1 - 1), TEAL, -1)
    return frame


def run_meter(meter, frame, start, n=3):
    events = []
    for i in range(n):
        events += meter.update(frame, start + i * 0.1)
    return events


def test_ability_drop_in_one_slot_fires():
    from valclip.detector import AbilityMeter

    meter = AbilityMeter()
    assert run_meter(meter, ability_frame(C=1.0, E=1.0), 0.0) == []
    events = run_meter(meter, ability_frame(C=1.0, E=0.5), 1.0)
    assert [e.kind for e in events] == [EventKind.ABILITY]


def test_ability_hidden_hud_and_multi_drop_do_not_fire():
    from valclip.detector import AbilityMeter

    meter = AbilityMeter()
    run_meter(meter, ability_frame(C=1.0, Q=1.0, E=1.0), 0.0)
    assert run_meter(meter, ability_frame(), 1.0) == []  # buy menu covers the HUD
    assert run_meter(meter, ability_frame(C=0.2, Q=0.2, E=0.2), 2.0) == []


def test_ability_refill_then_use():
    from valclip.detector import AbilityMeter

    meter = AbilityMeter()
    run_meter(meter, ability_frame(C=0.5), 0.0)
    assert run_meter(meter, ability_frame(C=1.0), 1.0) == []  # bought a charge
    assert len(run_meter(meter, ability_frame(C=0.5), 2.0)) == 1


def test_kill_feed_ignores_unpaired_yellow():
    import cv2

    from valclip.detector import KillFeedReader

    frame = feed_frame()
    cv2.line(frame, (1500, 200), (1600, 200), YELLOW, 2)  # e.g. a yellow shirt stripe
    assert KillFeedReader().read(frame) == (0, 0)


def test_ability_meter_resyncs_after_hud_change():
    from valclip.detector import AbilityMeter

    meter = AbilityMeter()
    run_meter(meter, ability_frame(C=1.0, Q=1.0, E=1.0), 0.0)
    run_meter(meter, ability_frame(C=0.5, Q=0.5, E=0.2), 1.0)  # now showing another player's HUD
    assert len(run_meter(meter, ability_frame(C=0.5, Q=0.5, E=0.0), 2.0)) == 1
