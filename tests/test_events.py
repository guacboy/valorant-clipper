from valclip.events import Event, EventKind, RoundTracker


def ev(kind, t):
    return Event(kind, t)


def test_death_triggers_with_round_events():
    tracker = RoundTracker()
    assert tracker.feed(ev(EventKind.ROUND_START, 0)) is None
    assert tracker.feed(ev(EventKind.KILL, 10)) is None
    log = tracker.feed(ev(EventKind.DEATH, 20))
    assert log is not None
    assert log.start == 0
    assert log.trigger_time == 20
    assert [e.kind for e in log.events] == [EventKind.KILL, EventKind.DEATH]


def test_round_end_triggers_when_alive():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    log = tracker.feed(ev(EventKind.ROUND_END, 90))
    assert log is not None and log.trigger_time == 90 and log.events == []


def test_only_one_trigger_per_round():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    assert tracker.feed(ev(EventKind.DEATH, 30)) is not None
    assert tracker.feed(ev(EventKind.KILL, 31)) is None
    assert tracker.feed(ev(EventKind.ROUND_END, 60)) is None


def test_new_round_resets():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    tracker.feed(ev(EventKind.KILL, 5))
    tracker.feed(ev(EventKind.DEATH, 10))
    tracker.feed(ev(EventKind.ROUND_START, 100))
    log = tracker.feed(ev(EventKind.ROUND_END, 190))
    assert log.start == 100 and log.events == []


def test_mid_round_start_has_no_start_time():
    log = RoundTracker().feed(ev(EventKind.DEATH, 5))
    assert log.start is None


def test_motion_kept_until_trigger():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    tracker.add_motion(1.0, 5.0)
    log = tracker.feed(ev(EventKind.DEATH, 2))
    tracker.add_motion(3.0, 9.0)
    assert log.motion == [(1.0, 5.0)]


def test_buy_phase_closes_round_when_alive():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 40))
    log = tracker.feed(ev(EventKind.BUY_PHASE, 145))
    assert log is not None and log.start == 40 and log.trigger_time == 145


def test_buy_menu_flicker_does_not_close_round():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 10))  # buy menu opened, banner hidden
    assert tracker.feed(ev(EventKind.BUY_PHASE, 13)) is None  # menu closed again
    assert tracker.feed(ev(EventKind.BUY_PHASE, 5)) is None


def test_buy_phase_without_round_start_is_ignored():
    assert RoundTracker().feed(ev(EventKind.BUY_PHASE, 100)) is None


def test_match_start_drops_unfinished_round():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    tracker.feed(ev(EventKind.KILL, 30))
    tracker.feed(ev(EventKind.MATCH_START, 400))
    assert tracker.feed(ev(EventKind.BUY_PHASE, 430)) is None  # no round is open in the new game


def test_buy_phase_long_after_round_start_is_ignored():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    assert tracker.feed(ev(EventKind.BUY_PHASE, 600)) is None  # next game's first buy phase


def test_round_end_after_death_is_ignored():
    tracker = RoundTracker()
    tracker.feed(ev(EventKind.ROUND_START, 0))
    assert tracker.feed(ev(EventKind.DEATH, 50)) is not None
    assert tracker.feed(ev(EventKind.ROUND_END, 80)) is None
