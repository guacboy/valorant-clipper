from valclip.events import EventKind
from valclip.scoring import Moment, group_moments, select_segments

K = EventKind.KILL


def test_multikill_groups_into_one_moment():
    moments = group_moments([(K, 10.0), (K, 11.5), (K, 13.0), (K, 30.0)])
    assert moments == [Moment(10.0, 13.0, 30.0), Moment(30.0, 30.0, 10.0)]


def test_unscored_events_are_ignored():
    assert group_moments([(EventKind.DEATH, 5.0), (EventKind.ROUND_END, 6.0)]) == []


def test_one_segment_per_slot_in_order_without_overlap():
    events = [(K, 20.0), (EventKind.ABILITY, 40.0), (K, 60.0), (EventKind.SPIKE_PLANT, 80.0)]
    segs = select_segments(events, [3.0, 3.0, 3.0, 3.0], (0.0, 100.0))
    assert [s.duration for s in segs] == [3.0] * 4
    assert all(a.end <= b.start for a, b in zip(segs, segs[1:]))
    for seg, t in zip(segs, [20.0, 40.0, 60.0, 80.0]):
        assert seg.start <= t <= seg.end


def test_best_moments_win_when_too_many():
    events = [(EventKind.ABILITY, 10.0), (K, 30.0), (K, 50.0)]
    segs = select_segments(events, [2.0, 2.0], (0.0, 100.0))
    assert all(s.start <= t <= s.end for s, t in zip(segs, [30.0, 50.0]))


def test_fillers_use_motion_peaks():
    motion = [(t / 4, 1.0) for t in range(400)]
    motion[200] = (50.0, 99.0)
    segs = select_segments([], [3.0], (0.0, 100.0), motion)
    assert segs[0].start <= 50.0 <= segs[0].end


def test_fillers_without_motion_are_spread_out():
    segs = select_segments([], [2.0, 2.0, 2.0], (0.0, 80.0))
    assert len(segs) == 3
    assert all(a.end <= b.start for a, b in zip(segs, segs[1:]))


def test_segments_stay_inside_window():
    segs = select_segments([(K, 0.5), (K, 99.8)], [4.0, 4.0], (0.0, 100.0))
    assert segs[0].start >= 0.0
    assert segs[-1].end <= 100.0


def test_short_round_still_fills_every_slot():
    segs = select_segments([], [3.0] * 4, (0.0, 6.0))
    assert len(segs) == 4
    assert all(0.0 <= s.start and s.end <= 6.0 for s in segs)
