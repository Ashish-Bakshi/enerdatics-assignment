"""Tests verifying that corrupt workbooks are caught and stop execution."""

import json
from pathlib import Path
import pytest
from watcher.source import SourceClient


def test_validate_workbook_rejects_corrupted_data():
    """Verify that corrupt or invalid files raise ValueError during download validation."""
    client = SourceClient(cache_dir="data/cache")

    # 1. Plain text / not a zip file
    with pytest.raises(ValueError, match="not a valid workbook"):
        client._validate_workbook(b"This is plain text, not a spreadsheet")

    # 2. Incomplete / truncated zip header
    with pytest.raises(ValueError, match="not a valid workbook"):
        client._validate_workbook(b"PK\x03\x04\x00\x00truncated content")


def test_cli_handles_corrupt_file_with_stopped_status(tmp_path, monkeypatch, watcher_cli):
    """End-to-end test verifying a corrupt file produces status STOPPED without changing baseline."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    report_path = tmp_path / "report.json"

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
""",
        encoding="utf-8",
    )

    class CorruptSourceClient:
        def fetch_page(self, url):
            return '<a href="/corrupt.xlsx">Unitil (August 2026)</a>'

        def download_workbook(self, url):
            raise ValueError("Downloaded file is not a valid workbook: not well-formed XML token")

    monkeypatch.setattr(watcher_cli, "SourceClient", CorruptSourceClient)
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

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "STOPPED"
    assert "not a valid workbook" in report["reason"]
    assert not (state_dir / "unitil.json").exists()
