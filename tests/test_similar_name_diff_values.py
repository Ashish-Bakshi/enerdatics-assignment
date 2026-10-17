"""Tests verifying that columns with similar names but different values are never auto-fixed."""

import json
from pathlib import Path
from watcher.schema import compare_schema


def test_similar_name_different_values_flags_needs_review():
    """Verify that a column with similar name (e.g. kW -> MW) but mismatched values
    is flagged as NEEDS_REVIEW and NEVER auto-applied.
    """
    baseline = {
        "columns": [
            "Facility ID (if any)",
            "City/Town",
            "Design Capacity (kW)",
            "Date Application Received",
        ],
        "records": [
            {
                "project_id": "P-101",
                "City/Town": "Boston",
                "Design Capacity (kW)": 500.0,
                "Date Application Received": "2026-01-15",
            },
            {
                "project_id": "P-102",
                "City/Town": "Worcester",
                "Design Capacity (kW)": 250.0,
                "Date Application Received": "2026-01-20",
            },
        ],
    }

    # Current month renamed column to "Design Capacity (MW)" with values scaled to MW (0.5 and 0.25)
    current = {
        "columns": [
            "Facility ID (if any)",
            "City/Town",
            "Design Capacity (MW)",
            "Date Application Received",
        ],
        "records": [
            {
                "project_id": "P-101",
                "City/Town": "Boston",
                "Design Capacity (MW)": 0.5,
                "Date Application Received": "2026-01-15",
            },
            {
                "project_id": "P-102",
                "City/Town": "Worcester",
                "Design Capacity (MW)": 0.25,
                "Date Application Received": "2026-01-20",
            },
        ],
    }

    required_columns = [
        "City/Town",
        "Design Capacity (kW)",
        "Date Application Received",
    ]

    result = compare_schema(baseline, current, required_columns)

    # Must be flagged for human review, NEVER auto-fixed
    assert result["status"] == "NEEDS_REVIEW"
    assert "different or unverifiable values" in result["reason"]
    assert "Design Capacity (kW)" not in result["column_map"]


def test_cli_rejects_similar_name_different_values(tmp_path, monkeypatch, watcher_cli):
    """End-to-end CLI test ensuring state and recipe are untouched on value mismatch."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    report_path = tmp_path / "report.json"

    # Pre-populate baseline with kW
    baseline_data = {
        "utility": "Unitil",
        "sha256": "old_sha",
        "sheet": "Sheet1",
        "header_row": 1,
        "columns": ["City/Town", "Design Capacity (Nameplate) (kW)"],
        "projects": 2,
        "records": [
            {"project_id": "1", "City/Town": "Fitchburg", "Design Capacity (Nameplate) (kW)": 100},
            {"project_id": "2", "City/Town": "Townsend", "Design Capacity (Nameplate) (kW)": 200},
        ],
    }
    (state_dir / "unitil.json").write_text(json.dumps(baseline_data), encoding="utf-8")

    recipe_path = tmp_path / "recipe.yaml"
    recipe_path.write_text(
        """
source: test
landing_url: https://example.com/test
utilities:
  Unitil:
    sheet: Sheet1
    id_column: Facility ID (if any)
    required_columns:
      - City/Town
      - Design Capacity (Nameplate) (kW)
""",
        encoding="utf-8",
    )

    class FakeClient:
        def fetch_page(self, url):
            return '<a href="/test.xlsx">Unitil (March 2026)</a>'

        def download_workbook(self, url):
            fake_wb = tmp_path / "fake.xlsx"
            fake_wb.write_bytes(b"dummy_content")
            return fake_wb

    monkeypatch.setattr(watcher_cli, "SourceClient", FakeClient)

    def fake_read_workbook(path, config, allow_missing=False):
        return {
            "sheet": "Sheet1",
            "header_row": 1,
            "columns": ["Facility ID (if any)", "City/Town", "Design Capacity (Nameplate) (MW)"],
            "projects": 2,
            "records": [
                {"project_id": "1", "City/Town": "Fitchburg", "Design Capacity (Nameplate) (MW)": 0.1},
                {"project_id": "2", "City/Town": "Townsend", "Design Capacity (Nameplate) (MW)": 0.2},
            ],
        }

    monkeypatch.setattr(watcher_cli, "read_workbook", fake_read_workbook)
    monkeypatch.setattr(
        "sys.argv",
        [
            "watcher.py",
            "--recipe", str(recipe_path),
            "--utility", "Unitil",
            "--month", "2026-03",
            "--state-dir", str(state_dir),
            "--report", str(report_path),
        ],
    )

    exit_code = watcher_cli.main()

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "NEEDS_REVIEW"
    assert "different or unverifiable values" in report["reason"]

    # Baseline remains the old version
    saved_baseline = json.loads((state_dir / "unitil.json").read_text(encoding="utf-8"))
    assert saved_baseline["sha256"] == "old_sha"
