"""Safety thresholds and validation rules for interconnection report watcher."""

# Thresholds chosen with data engineering rationale:
# 1. Utility interconnection queues are cumulative; project counts grow over time.
#    A sudden drop greater than 30% indicates truncation, data loss, or corrupted filters.
PROJECT_COUNT_DROP_THRESHOLD = 0.30

# 2. Existing columns should maintain consistent values for existing projects.
#    If more than 50% of matching projects have modified values, it signifies a semantic
#    or unit shift (e.g., kW to MW, or category re-encoding) that requires human review.
VALUE_CHANGE_THRESHOLD = 0.50

# 3. Candidate rename columns must have at least 60% normalized string similarity
#    to prevent mapping completely unrelated columns.
COLUMN_SIMILARITY_THRESHOLD = 0.60

# 4. A column rename is only safe to AUTO_FIX if at least 95% of common projects
#    have identical values when joined on Project ID.
VALUE_MATCH_THRESHOLD = 0.95


def check_project_count(previous_count: int, current_count: int) -> str | None:
    """Return an explanation if project count dropped beyond the safety threshold."""
    if previous_count <= 0:
        return None

    drop_fraction = (previous_count - current_count) / previous_count

    if drop_fraction > PROJECT_COUNT_DROP_THRESHOLD:
        return (
            f"Project count dropped from {previous_count} to {current_count}, "
            f"exceeding the {PROJECT_COUNT_DROP_THRESHOLD:.0%} threshold."
        )

    return None
