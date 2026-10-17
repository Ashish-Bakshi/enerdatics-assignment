"""Baseline storage and comparison for state management."""

import json
from pathlib import Path
import re


def baseline_path(state_dir: str | Path, utility: str) -> Path:
    """Generate the baseline file path for a utility."""
    slug = re.sub(r"[^a-z0-9]+", "-", utility.casefold()).strip("-")
    return Path(state_dir) / f"{slug}.json"


def load_baseline(state_dir: str | Path, utility: str) -> dict | None:
    """Load the saved baseline for a utility, or None if no baseline exists."""
    path = baseline_path(state_dir, utility)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as file:
        baseline = json.load(file)

    if baseline.get("utility") != utility:
        raise ValueError(
            f"Baseline utility mismatch in {path}: expected {utility!r}, "
            f"found {baseline.get('utility')!r}."
        )

    return baseline


def build_baseline(utility: str, sha256: str, result: dict) -> dict:
    """Construct a clean baseline dictionary from a processed workbook result."""
    return {
        "utility": utility,
        "sha256": sha256,
        "sheet": result["sheet"],
        "header_row": result["header_row"],
        "columns": result["columns"],
        "projects": result["projects"],
        "records": result["records"],
    }


def hash_matches(baseline: dict | None, sha256: str) -> bool:
    """Return True if the given SHA-256 matches the baseline hash."""
    return baseline is not None and baseline.get("sha256") == sha256


def save_baseline(state_dir: str | Path, utility: str, baseline: dict, status: str) -> Path:
    """Atomically save the baseline only after a safe run (OK or AUTO_FIXED)."""
    if status not in {"OK", "AUTO_FIXED"}:
        raise ValueError(
            f"Refusing to update baseline for unverified run status: {status!r}"
        )

    if baseline.get("utility") != utility:
        raise ValueError(
            f"Baseline utility mismatch: expected {utility!r}, got {baseline.get('utility')!r}"
        )

    path = baseline_path(state_dir, utility)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(baseline, file, indent=2, default=str)
        file.write("\n")

    temp_path.replace(path)
    return path
