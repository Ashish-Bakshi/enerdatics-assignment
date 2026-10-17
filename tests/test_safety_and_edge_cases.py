"""Tests covering project drop thresholds, duplicate file detection, 403 UA rotation, and headers."""

import hashlib
import json
from pathlib import Path
import pytest
import requests
from watcher.safety import check_project_count
from watcher.source import SourceClient, discover_file


def test_project_count_drop_threshold():
    """Verify that a drop in project count exceeding 30% generates a stop reason."""
    # 10% drop -> acceptable
    assert check_project_count(1000, 900) is None

    # 35% drop -> triggers stop reason
    stop_reason = check_project_count(1000, 650)
    assert stop_reason is not None
    assert "exceeding safety threshold" in stop_reason


def test_no_new_data_on_identical_sha(tmp_path, monkeypatch, watcher_cli):
    """Verify that identical SHA-256 results in status NO_NEW_DATA."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    report_path = tmp_path / "report.json"

    # Pre-populate baseline with matching sha
    baseline_data = {
        "utility": "Unitil",
        "sha256": "identical_sha_12345",
        "sheet": "Sheet1",
        "header_row": 1,
        "columns": ["Facility ID (if any)", "City/Town"],
        "projects": 100,
        "records": [],
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
""",
        encoding="utf-8",
    )

    class FakeClient:
        def fetch_page(self, url):
            return '<a href="/file.xlsx">Unitil (August 2026)</a>'

        def download_workbook(self, url):
            wb = tmp_path / "wb.xlsx"
            wb.write_bytes(b"content")
            return wb

    class MockHash:
        def hexdigest(self):
            return "identical_sha_12345"

    monkeypatch.setattr(watcher_cli, "SourceClient", FakeClient)
    monkeypatch.setattr(watcher_cli.hashlib, "sha256", lambda b: MockHash())

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
    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "NO_NEW_DATA"


def test_source_client_rotates_user_agent_on_403(monkeypatch):
    """Verify that SourceClient retries with another User-Agent upon receiving 403."""
    client = SourceClient(cache_dir="data/cache", min_interval=0.0)

    used_user_agents = []

    def mock_get(url, headers=None, timeout=None, allow_redirects=None):
        ua = headers.get("User-Agent")
        used_user_agents.append(ua)

        resp = requests.Response()
        resp.url = url
        if len(used_user_agents) == 1:
            resp.status_code = 403
        else:
            resp.status_code = 200
            resp._content = b"<html>OK</html>"
        return resp

    monkeypatch.setattr(client.session, "get", mock_get)

    page = client.fetch_page("https://example.com/landing")
    assert page == "<html>OK</html>"
    assert len(used_user_agents) == 2
    assert used_user_agents[0] != used_user_agents[1]


def test_discover_file_matching():
    """Verify discovery logic handles label variations and case sensitivity."""
    html = """
    <html>
      <body>
        <a href="/doc/unitil-august.xlsx">Unitil (August 2026)</a>
        <a href="/doc/eversource-east-august.xlsx">Eversource East (August 2026)</a>
        <a href="/doc/eversource-west-august.xlsx">Eversource West (August 2026)</a>
      </body>
    </html>
    """
    url_unitil = discover_file(html, "https://example.com", "Unitil", "2026-08")
    assert url_unitil == "https://example.com/doc/unitil-august.xlsx"

    url_ev_east = discover_file(html, "https://example.com", "Eversource East", "2026-08")
    assert url_ev_east == "https://example.com/doc/eversource-east-august.xlsx"

    with pytest.raises(LookupError):
        discover_file(html, "https://example.com", "Unitil", "2026-12")
