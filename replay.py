#!/usr/bin/env python3
"""Automated replay runner for the 16 monthly runs (Unitil and Eversource East)."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


MONTHS = [
    "2026-01",
    "2026-02",
    "2026-03",
    "2026-04",
    "2026-05",
    "2026-06",
    "2026-07",
    "2026-08",
]


def run_replay(utility: str, recipe_path: str = "recipe.yaml", state_dir: str = "state", reports_dir: str = "reports"):
    """Run monthly replay in sequence for a utility."""
    print("=" * 80)
    print(f"REPLAYING INTERCONNECTION WATCHER FOR: {utility.upper()}")
    print("=" * 80)

    for month in MONTHS:
        report_file = Path(reports_dir) / f"{utility.lower().replace(' ', '_')}_{month}.json"
        cmd = [
            sys.executable,
            "watcher.py",
            "--recipe", recipe_path,
            "--utility", utility,
            "--month", month,
            "--state-dir", state_dir,
            "--report", str(report_file),
        ]

        print(f"\n▶ [{month}] Running command: {' '.join(cmd)}")

        # Prevent a previous run's report from being mistaken for a fresh result.
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.unlink(missing_ok=True)

        result = subprocess.run(cmd, capture_output=True, text=True)

        try:
            if not report_file.exists():
                raise FileNotFoundError(
                    f"Watcher produced no report (exit code {result.returncode})."
                )
            
            report = json.loads(report_file.read_text(encoding="utf-8"))
            status = report.get("status")
            reason = report.get("reason")
            projects = report.get("projects")
            header_row = report.get("header_row")
            changes = report.get("changes")

            status_symbol = {
                "OK": "✔ OK",
                "AUTO_FIXED": "⚡ AUTO_FIXED",
                "NEEDS_REVIEW": "⚠ NEEDS_REVIEW",
                "STOPPED": "✖ STOPPED",
                "NO_NEW_DATA": "⏸ NO_NEW_DATA",
            }.get(status, status)

            print(f"   Status:     {status_symbol}")
            print(f"   Header Row: {header_row} | Projects: {projects}")
            print(f"   Reason:     {reason}")
            if changes:
                print(f"   Changes:    {changes}")
        except Exception as exc:
            print(f"   Replay error: {exc}")
            if result.stdout:
                print(f"   Result Output:\n{result.stdout}")
            if result.stderr:
                print(f"   Error:\n{result.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Replay monthly watcher runs.")
    parser.add_argument(
        "--utility",
        choices=["Unitil", "Eversource East", "all"],
        default="all",
        help="Target utility to replay (default: all).",
    )
    args = parser.parse_args()

    utilities = ["Unitil", "Eversource East"] if args.utility == "all" else [args.utility]
    for u in utilities:
        run_replay(u)


if __name__ == "__main__":
    main()
