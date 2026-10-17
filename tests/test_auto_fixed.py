"""Tests verifying safe column rename auto-fixing and recipe updates."""

import json
from pathlib import Path
import yaml
from watcher.schema import compare_schema


def test_safe_column_rename_auto_fixed():
    """Verify that a missing column with similar name and matching values is AUTO_FIXED."""
    baseline = {
        "columns": ["City/Town", "Fuel Type (Solar, Wind, etc)"],
        "records": [
            {"project_id": "1", "City/Town": "Boston", "Fuel Type (Solar, Wind, etc)": "Solar"},
            {"project_id": "2", "City/Town": "Cambridge", "Fuel Type (Solar, Wind, etc)": "Wind"},
        ],
    }

    current = {
        "columns": ["City/Town", "Fuel Type"],
        "records": [
            {"project_id": "1", "City/Town": "Boston", "Fuel Type": "Solar"},
            {"project_id": "2", "City/Town": "Cambridge", "Fuel Type": "Wind"},
        ],
    }

    required = ["City/Town", "Fuel Type (Solar, Wind, etc)"]
    result = compare_schema(baseline, current, required)

    assert result["status"] == "AUTO_FIXED"
    assert result["column_map"]["Fuel Type (Solar, Wind, etc)"] == "Fuel Type"
    assert len(result["changes"]) == 1
    assert result["changes"][0]["type"] == "COLUMN_RENAMED"


def test_cli_auto_fixed_updates_recipe_and_baseline(tmp_path, monkeypatch, watcher_cli):
    """Verify CLI updates recipe file in state and updates baseline."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    report_path = tmp_path / "report.json"

    baseline_data = {
        "utility": "Unitil",
        "sha256": "sha_feb",
        "sheet": "Sheet1",
        "header_row": 21,
        "columns": ["Facility ID (if any)", "City/Town", "Fuel Type (Solar, Wind, etc)"],
        "projects": 2,
        "records": [
            {"project_id": "1", "City/Town": "Fitchburg", "Fuel Type (Solar, Wind, etc)": "Solar"},
            {"project_id": "2", "City/Town": "Townsend", "Fuel Type (Solar, Wind, etc)": "Solar"},
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
      - Fuel Type (Solar, Wind, etc)
""",
        encoding="utf-8",
    )

    class FakeClient:
        def fetch_page(self, url):
            return '<a href="/unitil-mar.xlsx">Unitil (March 2026)</a>'

        def download_workbook(self, url):
            fake_wb = tmp_path / "fake.xlsx"
            fake_wb.write_bytes(b"march_content")
            return fake_wb

    monkeypatch.setattr(watcher_cli, "SourceClient", FakeClient)

    def fake_read_workbook(path, config, allow_missing=False):
        return {
            "sheet": "Sheet1",
            "header_row": 1,
            "columns": ["Facility ID (if any)", "City/Town", "Fuel Type"],
            "projects": 2,
            "records": [
                {"project_id": "1", "City/Town": "Fitchburg", "Fuel Type": "Solar"},
                {"project_id": "2", "City/Town": "Townsend", "Fuel Type": "Solar"},
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

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "AUTO_FIXED"
    assert report["column_map"]["Fuel Type (Solar, Wind, etc)"] == "Fuel Type"

    # State recipe must be updated with the new column name
    updated_recipe = yaml.safe_load((state_dir / "recipe.yaml").read_text(encoding="utf-8"))
    assert "Fuel Type" in updated_recipe["utilities"]["Unitil"]["required_columns"]
    assert "Fuel Type (Solar, Wind, etc)" not in updated_recipe["utilities"]["Unitil"]["required_columns"]

    # Baseline is updated
    new_baseline = json.loads((state_dir / "unitil.json").read_text(encoding="utf-8"))
    assert new_baseline["sha256"] != "sha_feb"
