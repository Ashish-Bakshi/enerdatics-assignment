import json
import subprocess
from pathlib import Path

import replay


def test_replay_does_not_use_stale_report(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    stale_report = reports_dir / "unitil_2026-01.json"
    stale_report.write_text(
        json.dumps({
            "utility": "Unitil",
            "month": "2026-01",
            "status": "OK",
            "reason": "Old report",
            "projects": 100,
            "header_row": 1,
            "changes": [],
        }),
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        # Simulate the watcher failing without producing a new report.
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Simulated failure",
        )

    monkeypatch.setattr(replay.subprocess, "run", fake_run)

    replay.run_replay(
        utility="Unitil",
        state_dir=str(tmp_path / "state"),
        reports_dir=str(reports_dir),
    )

    output = capsys.readouterr().out

    assert "Old report" not in output
    assert "Watcher produced no report" in output
    assert not stale_report.exists()
