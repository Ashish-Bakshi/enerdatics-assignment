#!/usr/bin/env python3
"""Self-Healing Data Source Watcher CLI.

Detects schema, header, and data shifts in utility monthly interconnection filings,
automatically applies safe column renames to the recipe state, and flags risky changes.
"""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

from watcher.baseline import (
    build_baseline,
    hash_matches,
    load_baseline,
    save_baseline,
)
from watcher.recipe import (
    get_active_recipe_path,
    get_utility_config,
    load_recipe,
    update_recipe_column,
)
from watcher.safety import check_project_count
from watcher.schema import compare_schema
from watcher.source import SourceClient, discover_file
from watcher.workbook import read_workbook


def parse_args():
    """Parse required command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Self-healing watcher for utility interconnection reports."
    )
    parser.add_argument(
        "--recipe",
        required=True,
        help="Path to starting recipe YAML file.",
    )
    parser.add_argument(
        "--utility",
        required=True,
        help="Target utility name (e.g. 'Unitil', 'Eversource East').",
    )
    parser.add_argument(
        "--month",
        required=True,
        help="Report month in YYYY-MM format (e.g. '2026-03').",
    )
    parser.add_argument(
        "--state-dir",
        required=True,
        help="Directory to persist baseline state and recipe versions.",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Output path for JSON report.",
    )
    return parser.parse_args()


def write_report(report_path: str | Path, report_data: dict) -> None:
    """Safely write JSON report to destination, creating parent directories."""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(report_data, file, indent=2, default=str)
        file.write("\n")


def normalize_records(records: list[dict], column_map: dict, target_columns: list[str]) -> list[dict]:
    """Map project records to target required column names."""
    normalized = []
    for record in records:
        row = {"project_id": record["project_id"]}
        for col in target_columns:
            # If target column exists directly in raw record
            if col in record:
                row[col] = record[col]
            else:
                # Find matching actual column from column_map
                actual_col = column_map.get(col, col)
                row[col] = record.get(actual_col)
        normalized.append(row)
    return normalized


def main() -> int:
    args = parse_args()

    report = {
        "utility": args.utility,
        "month": args.month,
        "status": "STOPPED",
        "reason": "Processing did not complete.",
        "file_url": None,
        "sha256": None,
        "sheet": None,
        "header_row": None,
        "projects": 0,
        "column_map": {},
        "changes": [],
    }

    try:
        # 1. Validate month format
        try:
            parsed_month = datetime.strptime(args.month, "%Y-%m")
        except ValueError as exc:
            raise ValueError(
                f"Invalid month {args.month!r}; expected format is YYYY-MM."
            ) from exc

        if parsed_month.strftime("%Y-%m") != args.month:
            raise ValueError(
                f"Invalid month {args.month!r}; expected format is YYYY-MM."
            )

        # 2. Setup state directory and active recipe
        state_dir = Path(args.state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)

        active_recipe_path = get_active_recipe_path(state_dir, args.recipe)
        recipe = load_recipe(active_recipe_path)
        config = get_utility_config(recipe, args.utility)

        # 3. Load baseline for comparison
        baseline = load_baseline(state_dir, args.utility)

        # 4. Fetch landing page and discover file link
        client = SourceClient()
        landing_url = recipe["landing_url"]
        page_html = client.fetch_page(landing_url)

        file_url = discover_file(
            page_html,
            landing_url,
            args.utility,
            args.month,
        )
        report["file_url"] = file_url

        # 5. Download workbook with validation & SHA computation
        workbook_path = client.download_workbook(file_url)
        file_bytes = workbook_path.read_bytes()
        sha256 = hashlib.sha256(file_bytes).hexdigest()
        report["sha256"] = sha256

        # 6. Check for duplicate file (NO_NEW_DATA)
        if hash_matches(baseline, sha256):
            report.update({
                "status": "NO_NEW_DATA",
                "reason": "Workbook SHA-256 matches the saved baseline.",
                "sheet": baseline["sheet"],
                "header_row": baseline["header_row"],
                "projects": baseline["projects"],
                "column_map": {
                    col: col for col in config["required_columns"]
                },
            })
        else:
            # 7. Read and parse workbook
            result = read_workbook(
                workbook_path,
                config,
                allow_missing=True,
            )

            report["sheet"] = result["sheet"]
            report["header_row"] = result["header_row"]
            report["projects"] = result["projects"]

            # 8. Check project count safety threshold
            if baseline is not None:
                count_stop_reason = check_project_count(
                    baseline["projects"],
                    result["projects"],
                )
                if count_stop_reason:
                    report.update({
                        "status": "STOPPED",
                        "reason": count_stop_reason,
                        "column_map": {},
                        "changes": [],
                    })
                    write_report(args.report, report)
                    print(json.dumps(report, indent=2, default=str))
                    return 1

            # 9. Schema and value comparison
            comparison = compare_schema(
                baseline,
                result,
                config["required_columns"],
            )

            report.update({
                "status": comparison["status"],
                "reason": comparison["reason"],
                "column_map": comparison["column_map"],
                "changes": comparison["changes"],
            })

            # 10. State updates for accepted runs
            if report["status"] == "AUTO_FIXED":
                # Compute updated required columns list with new column names
                updated_columns = [
                    comparison["column_map"].get(col, col)
                    for col in config["required_columns"]
                ]

                # Update recipe in state with renamed columns
                for change in comparison["changes"]:
                    if change.get("type") == "COLUMN_RENAMED":
                        update_recipe_column(
                            state_dir,
                            args.utility,
                            change["from"],
                            change["to"],
                        )

                # Normalize records and persist updated baseline using new schema
                normalized = dict(result)
                normalized["records"] = normalize_records(
                    result["records"],
                    comparison["column_map"],
                    updated_columns,
                )
                normalized["columns"] = updated_columns

                new_baseline = build_baseline(
                    args.utility,
                    sha256,
                    normalized,
                )
                save_baseline(
                    state_dir,
                    args.utility,
                    new_baseline,
                    report["status"],
                )

            elif report["status"] == "OK":
                normalized = dict(result)
                normalized["records"] = normalize_records(
                    result["records"],
                    comparison["column_map"],
                    config["required_columns"],
                )
                normalized["columns"] = config["required_columns"]

                new_baseline = build_baseline(
                    args.utility,
                    sha256,
                    normalized,
                )
                save_baseline(
                    state_dir,
                    args.utility,
                    new_baseline,
                    report["status"],
                )

    except Exception as exc:
        report["status"] = "STOPPED"
        report["reason"] = str(exc)

    try:
        write_report(args.report, report)
    except OSError as exc:
        print(f"Could not write report: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, default=str))

    if report["status"] in {"OK", "NO_NEW_DATA", "AUTO_FIXED"}:
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
