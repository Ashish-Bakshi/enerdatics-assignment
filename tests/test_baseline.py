import json

import pytest

from watcher.baseline import (
    build_baseline,
    hash_matches,
    load_baseline,
    save_baseline,
)


def sample_result():
    return {
        "sheet": "Sheet1",
        "header_row": 3,
        "columns": [
            "Facility ID (if any)",
            "City/Town",
            "Capacity",
        ],
        "projects": 1,
        "records": [
            {
                "project_id": "P-001",
                "City/Town": "Boston",
                "Capacity": 250,
            }
        ],
    }


def test_missing_baseline_returns_none(tmp_path):
    assert load_baseline(tmp_path, "Unitil") is None


def test_baseline_round_trip(tmp_path):
    baseline = build_baseline(
        "Unitil",
        "abc123",
        sample_result(),
    )

    save_baseline(tmp_path, "Unitil", baseline, "OK")
    loaded = load_baseline(tmp_path, "Unitil")

    assert loaded == baseline
    assert loaded["projects"] == 1
    assert loaded["records"][0]["project_id"] == "P-001"


def test_hash_comparison():
    baseline = {"sha256": "abc123"}

    assert hash_matches(baseline, "abc123")
    assert not hash_matches(baseline, "different")
    assert not hash_matches(None, "abc123")


@pytest.mark.parametrize("status", ["NEEDS_REVIEW", "STOPPED", "NO_NEW_DATA"])
def test_unaccepted_status_cannot_overwrite_baseline(tmp_path, status):
    original = build_baseline("Unitil", "original-hash", sample_result())
    save_baseline(tmp_path, "Unitil", original, "OK")

    replacement = build_baseline("Unitil", "new-hash", sample_result())

    with pytest.raises(ValueError, match="Cannot update baseline"):
        save_baseline(tmp_path, "Unitil", replacement, status)

    loaded = load_baseline(tmp_path, "Unitil")
    assert loaded["sha256"] == "original-hash"


def test_baselines_are_separate_per_utility(tmp_path):
    unitil = build_baseline("Unitil", "unitil-hash", sample_result())
    eversource = build_baseline(
        "Eversource East",
        "eversource-hash",
        sample_result(),
    )

    save_baseline(tmp_path, "Unitil", unitil, "OK")
    save_baseline(tmp_path, "Eversource East", eversource, "OK")

    assert load_baseline(tmp_path, "Unitil")["sha256"] == "unitil-hash"
    assert (
        load_baseline(tmp_path, "Eversource East")["sha256"]
        == "eversource-hash"
    )


def test_baseline_is_valid_json(tmp_path):
    baseline = build_baseline("Unitil", "abc123", sample_result())
    save_baseline(tmp_path, "Unitil", baseline, "OK")

    path = tmp_path / "unitil.json"
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["utility"] == "Unitil"
    assert saved["sha256"] == "abc123"
