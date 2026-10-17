"""Tests verifying value shift detection for existing columns."""

import json
from pathlib import Path
from watcher.schema import compare_schema
import watcher


def test_changed_values_flags_needs_review():
    """Verify that when more than 50% of matching projects have changed values in a column,
    the run ends with NEEDS_REVIEW.
    """
    baseline = {
        "columns": ["City/Town", "Fuel Type (PV, Wind, etc)"],
        "records": [
            {"project_id": "1", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "PV"},
            {"project_id": "2", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "PV"},
            {"project_id": "3", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "PV"},
            {"project_id": "4", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "Wind"},
        ],
    }

    # 3 out of 4 projects (75%) changed from "PV" to "Solar"
    current = {
        "columns": ["City/Town", "Fuel Type (PV, Wind, etc)"],
        "records": [
            {"project_id": "1", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "Solar"},
            {"project_id": "2", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "Solar"},
            {"project_id": "3", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "Solar"},
            {"project_id": "4", "City/Town": "Boston", "Fuel Type (PV, Wind, etc)": "Wind"},
        ],
    }

    required = ["City/Town", "Fuel Type (PV, Wind, etc)"]
    result = compare_schema(baseline, current, required)

    assert result["status"] == "NEEDS_REVIEW"
    assert "Values changed for 75%" in result["reason"]
    assert result["changes"][0]["type"] == "VALUES_CHANGED"
    assert result["changes"][0]["changed_fraction"] == 0.75
