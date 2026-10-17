from watcher.safety import check_project_count


def test_stops_when_project_count_drops_more_than_30_percent():
    reason = check_project_count(100, 60)

    assert reason is not None
    assert "exceeding the 30% threshold" in reason


def test_allows_project_count_drop_within_threshold():
    assert check_project_count(100, 85) is None


def test_allows_exactly_30_percent_drop():
    assert check_project_count(100, 70) is None


def test_zero_previous_count_does_not_trigger_drop():
    assert check_project_count(0, 0) is None
