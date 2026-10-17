"""Schema comparison, column rename detection, and value consistency verification."""

from datetime import date, datetime
from difflib import SequenceMatcher
import re

from watcher.safety import (
    COLUMN_SIMILARITY_THRESHOLD,
    VALUE_CHANGE_THRESHOLD,
    VALUE_MATCH_THRESHOLD,
)


def values_equal(val1, val2) -> bool:
    """Compare two cell values accounting for serialization and type coercion differences."""
    if val1 is None and val2 is None:
        return True

    # Treat empty strings and None as equivalent empty values
    s1 = str(val1).strip() if val1 is not None else ""
    s2 = str(val2).strip() if val2 is not None else ""
    if not s1 and not s2:
        return True

    if s1 == s2:
        return True

    # Format datetime/date objects to standard string representation
    if isinstance(val1, (datetime, date)):
        s1 = val1.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val2, (datetime, date)):
        s2 = val2.strftime("%Y-%m-%d %H:%M:%S")
    if s1 == s2:
        return True

    # Compare numeric values (e.g. 10 vs 10.0 or string "10.0")
    try:
        f1 = float(s1)
        f2 = float(s2)
        return abs(f1 - f2) < 1e-5
    except (ValueError, TypeError):
        pass

    return False


def column_similarity(expected: str, candidate: str) -> float:
    """Compute semantic string similarity between two column names.
    
    Handles parenthetical descriptions/units (e.g. 'Fuel Type (Solar, Wind, etc)' vs 'Fuel Type',
    or 'Design Capacity (kW)' vs 'Design Capacity (MW)').
    """
    # 1. Base name comparison without parenthetical units/examples
    base_exp = re.sub(r"\(.*?\)", "", expected).strip().casefold()
    base_cand = re.sub(r"\(.*?\)", "", candidate).strip().casefold()
    if base_exp and base_cand and base_exp == base_cand:
        return 0.95

    # 2. Normalized alphanumeric sequence matcher
    norm_exp = "".join(c.lower() for c in expected if c.isalnum())
    norm_cand = "".join(c.lower() for c in candidate if c.isalnum())
    if not norm_exp or not norm_cand:
        return 0.0

    ratio = SequenceMatcher(None, norm_exp, norm_cand).ratio()

    # 3. Substring containment boost
    if (norm_cand in norm_exp or norm_exp in norm_cand) and min(len(norm_cand), len(norm_exp)) >= 6:
        sub_ratio = min(len(norm_cand), len(norm_exp)) / max(len(norm_cand), len(norm_exp))
        ratio = max(ratio, 0.50 + 0.50 * sub_ratio)

    return ratio


def similar_column(expected: str, available_columns: list[str] | set[str]) -> str | None:
    """Find the best plausible replacement column name above similarity threshold."""
    candidates = []

    for col in available_columns:
        similarity = column_similarity(expected, col)
        if similarity >= COLUMN_SIMILARITY_THRESHOLD:
            candidates.append((similarity, col))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_col = candidates[0]

    # Reject ambiguous ties rather than guessing silently
    if len(candidates) > 1 and candidates[1][0] == best_score:
        return None

    return best_col


def verify_renamed_column_values(
    baseline_records: list[dict],
    current_records: list[dict],
    old_column: str,
    new_column: str,
) -> tuple[bool, float, int]:
    """Join on project ID with baseline and check whether values match.
    
    Returns (is_safe, match_rate, common_project_count).
    """
    old_values = {
        r["project_id"]: r.get(old_column)
        for r in baseline_records
    }
    new_values = {
        r["project_id"]: r.get(new_column)
        for r in current_records
    }

    common_ids = set(old_values.keys()) & set(new_values.keys())
    if not common_ids:
        return False, 0.0, 0

    matching = sum(1 for pid in common_ids if values_equal(old_values[pid], new_values[pid]))
    match_rate = matching / len(common_ids)
    is_safe = match_rate >= VALUE_MATCH_THRESHOLD

    return is_safe, match_rate, len(common_ids)


def changed_value_fraction(
    baseline_records: list[dict],
    current_records: list[dict],
    column: str,
) -> tuple[float | None, int]:
    """Calculate the fraction of common projects with modified values for an existing column."""
    old_values = {
        r["project_id"]: r.get(column)
        for r in baseline_records
    }
    new_values = {
        r["project_id"]: r.get(column)
        for r in current_records
    }

    common_ids = set(old_values.keys()) & set(new_values.keys())
    if not common_ids:
        return None, 0

    changed = sum(1 for pid in common_ids if not values_equal(old_values[pid], new_values[pid]))
    return changed / len(common_ids), len(common_ids)


def compare_schema(
    baseline: dict | None,
    current: dict,
    required_columns: list[str],
) -> dict:
    """Compare required columns and detect safe renames or unsafe value drift."""
    current_columns = set(current.get("columns", []))
    column_map = {}
    changes = []

    # If this is the initial run (no baseline exists)
    if baseline is None:
        missing = [col for col in required_columns if col not in current_columns]
        if missing:
            return {
                "status": "NEEDS_REVIEW",
                "reason": f"Initial workbook missing required columns: {', '.join(missing)}",
                "column_map": {},
                "changes": [],
            }
        return {
            "status": "OK",
            "reason": "Initial workbook parsed successfully.",
            "column_map": {col: col for col in required_columns},
            "changes": [],
        }

    baseline_records = baseline.get("records", [])
    current_records = current.get("records", [])

    for expected in required_columns:
        if expected in current_columns:
            column_map[expected] = expected

            # Check if values for this column shifted significantly (> 50%)
            frac_changed, common_count = changed_value_fraction(
                baseline_records,
                current_records,
                expected,
            )

            if frac_changed is not None and frac_changed > VALUE_CHANGE_THRESHOLD:
                return {
                    "status": "NEEDS_REVIEW",
                    "reason": (
                        f"Values changed for {frac_changed:.0%} of comparable projects "
                        f"in column {expected!r}."
                    ),
                    "column_map": column_map,
                    "changes": [{
                        "type": "VALUES_CHANGED",
                        "column": expected,
                        "changed_fraction": frac_changed,
                        "comparable_projects": common_count,
                    }],
                }
            continue

        # Column is missing: check for candidate replacement
        replacement = similar_column(expected, current_columns)
        if replacement is None:
            return {
                "status": "NEEDS_REVIEW",
                "reason": f"Required column {expected!r} is missing from sheet.",
                "column_map": column_map,
                "changes": changes,
            }

        is_safe, match_rate, common_count = verify_renamed_column_values(
            baseline_records,
            current_records,
            expected,
            replacement,
        )

        if not is_safe:
            return {
                "status": "NEEDS_REVIEW",
                "reason": (
                    f"Possible replacement {replacement!r} for {expected!r} "
                    f"has different values ({1 - match_rate:.1%} mismatch across "
                    f"{common_count} projects)."
                ),
                "column_map": column_map,
                "changes": [{
                    "type": "COLUMN_RENAME_REJECTED",
                    "from": expected,
                    "to": replacement,
                    "match_rate": match_rate,
                }],
            }

        column_map[expected] = replacement
        changes.append({
            "type": "COLUMN_RENAMED",
            "from": expected,
            "to": replacement,
            "match_rate": match_rate,
            "joined_projects": common_count,
        })

    status = "AUTO_FIXED" if changes else "OK"
    reason = (
        f"Safely mapped {len(changes)} renamed column(s)."
        if changes
        else "Required columns and values matched baseline."
    )

    return {
        "status": status,
        "reason": reason,
        "column_map": column_map,
        "changes": changes,
    }
