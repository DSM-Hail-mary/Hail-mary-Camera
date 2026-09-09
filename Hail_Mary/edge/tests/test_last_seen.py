from Hail_Mary.edge.last_seen import LastSeenTracker


def test_first_update_with_zero_count_is_not_a_transition():
    tracker = LastSeenTracker()

    assert tracker.update("hall_main", 0, now=1000.0) is False


def test_first_update_with_positive_count_is_not_a_transition():
    tracker = LastSeenTracker()

    assert tracker.update("hall_main", 3, now=1000.0) is False


def test_transition_from_positive_to_zero_returns_true():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)

    assert tracker.update("hall_main", 0, now=1001.0) is True


def test_staying_at_zero_is_not_a_transition():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)
    tracker.update("hall_main", 0, now=1001.0)

    assert tracker.update("hall_main", 0, now=1002.0) is False


def test_staying_positive_is_not_a_transition():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)

    assert tracker.update("hall_main", 5, now=1001.0) is False


def test_zero_to_positive_is_not_a_transition():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 0, now=1000.0)

    assert tracker.update("hall_main", 4, now=1001.0) is False


def test_zones_are_tracked_independently():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)
    tracker.update("entrance", 1, now=1000.0)

    assert tracker.update("hall_main", 0, now=1001.0) is True
    assert tracker.update("entrance", 3, now=1001.0) is False
    assert tracker.update("entrance", 0, now=1002.0) is True


def test_re_transition_after_refill_returns_true_again():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)
    assert tracker.update("hall_main", 0, now=1001.0) is True

    tracker.update("hall_main", 1, now=1002.0)

    assert tracker.update("hall_main", 0, now=1003.0) is True
