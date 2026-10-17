import json
import hashlib

from watcher.recipe import get_utility_config, load_recipe
from watcher.schema import compare_schema
from pathlib import Path

import importlib.util

spec = importlib.util.spec_from_file_location(
    "watcher_cli",
    Path(__file__).resolve().parents[1] / "watcher.py",
)
watcher_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher_cli)

def test_recipe_and_utility_configuration_work_together():
    recipe = load_recipe("recipe.yaml")
    config = get_utility_config(recipe, "Unitil")

    assert recipe["landing_url"].startswith("https://")
    assert config["sheet"] == "Sheet1"


def test_eversource_configuration_is_available():
    recipe = load_recipe("recipe.yaml")
    config = get_utility_config(recipe, "Eversource East")

    assert config["sheet"] == "Tracking Sheet"
    assert len(config["required_columns"]) == 4

def test_missing_column_without_baseline_requires_review():
    required_columns = [
        "City/Town",
        "Design Capacity (Nameplate) (kW)",
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ]

    current = {
        "columns": [
            "Facility ID (if any)",
            "City/Town",
            "Design Capacity (Nameplate) (kW)",
            "Fuel Type",
            "Date Application Received",
        ],
        "records": [
            {
                "project_id": "1001",
                "City/Town": "Boston",
                "Design Capacity (Nameplate) (kW)": 10,
                "Fuel Type": "Solar",
                "Date Application Received": "2026-08-01",
            }
        ],
    }

    # Without a baseline, there is no historical evidence that the
    # replacement column contains equivalent values.
    baseline = {
        "records": [],
    }

    result = compare_schema(
        baseline,
        current,
        required_columns,
    )

    assert result["status"] == "NEEDS_REVIEW"
    assert "Fuel Type (Solar, Wind, etc)" not in result["column_map"]

def test_initial_missing_column_requires_review_without_baseline(
    tmp_path, monkeypatch
):
    workbook_path = Path("data/cache/unitil-2026-08.xlsx")
    assert workbook_path.exists(), "Cached Unitil August workbook is required"

    recipe_path = Path("recipe.yaml")
    state_dir = tmp_path / "state"
    report_path = tmp_path / "report.json"

    class FakeSourceClient:
        def fetch_page(self, url):
            return "<html><body>test page</body></html>"

        def download_workbook(self, url):
            return workbook_path

    monkeypatch.setattr(
        watcher_cli,
        "SourceClient",
        FakeSourceClient,
    )
    monkeypatch.setattr(
        watcher_cli,
        "discover_file",
        lambda *args: "https://example.com/unitil-august.xlsx",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "watcher.py",
            "--recipe", str(recipe_path),
            "--utility", "Unitil",
            "--month", "2026-08",
            "--state-dir", str(state_dir),
            "--report", str(report_path),
        ],
    )

    exit_code = watcher_cli.main()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["status"] == "NEEDS_REVIEW"
    assert report["projects"] == 1431
    assert report["sha256"] == hashlib.sha256(
        workbook_path.read_bytes()
    ).hexdigest()
    assert not (state_dir / "unitil.json").exists()