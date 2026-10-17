from watcher.schema import compare_schema
from watcher.schema import changed_value_fraction

REQUIRED_COLUMNS = [
    "City/Town",
    "Design Capacity (Nameplate) (kW)",
    "Fuel Type (Solar, Wind, etc)",
    "Date Application Received",
]


def make_result(columns, capacity_column):
    return {
        "columns": columns,
        "records": [
            {
                "project_id": "P-001",
                "City/Town": "Boston",
                capacity_column: 250,
                "Fuel Type (Solar, Wind, etc)": "Solar",
                "Date Application Received": "2026-01-15",
            },
            {
                "project_id": "P-002",
                "City/Town": "Salem",
                capacity_column: 500,
                "Fuel Type (Solar, Wind, etc)": "Solar",
                "Date Application Received": "2026-01-20",
            },
        ],
    }


def test_unchanged_schema_returns_ok():
    columns = [
        "Facility ID (if any)",
        *REQUIRED_COLUMNS,
    ]
    baseline = make_result(columns, REQUIRED_COLUMNS[1])
    current = make_result(columns, REQUIRED_COLUMNS[1])

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "OK"
    assert result["changes"] == []


def test_renamed_column_with_matching_values_is_auto_fixed():
    old_capacity = "Design Capacity (Nameplate) (kW)"
    new_capacity = "Nameplate Design Capacity (kW)"

    baseline_columns = [
        "Facility ID (if any)",
        *REQUIRED_COLUMNS,
    ]
    current_columns = [
        "Facility ID (if any)",
        "City/Town",
        new_capacity,
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ]

    baseline = make_result(baseline_columns, old_capacity)
    current = make_result(current_columns, new_capacity)

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "AUTO_FIXED"
    assert result["column_map"][old_capacity] == new_capacity
    assert result["changes"][0]["type"] == "COLUMN_RENAMED"


def test_similar_column_with_different_values_needs_review():
    old_capacity = "Design Capacity (Nameplate) (kW)"
    new_capacity = "Design Capacity Nameplate MW"

    baseline_columns = ["Facility ID (if any)", *REQUIRED_COLUMNS]
    current_columns = [
        "Facility ID (if any)",
        "City/Town",
        new_capacity,
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ]

    baseline = make_result(baseline_columns, old_capacity)
    current = make_result(current_columns, new_capacity)

    current["records"][0][new_capacity] = 0.25
    current["records"][1][new_capacity] = 0.5

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "NEEDS_REVIEW"
    assert "different or unverifiable values" in result["reason"]


def test_missing_column_without_plausible_replacement_needs_review():
    baseline = make_result(
        ["Facility ID (if any)", *REQUIRED_COLUMNS],
        REQUIRED_COLUMNS[1],
    )

    current_columns = [
        "Facility ID (if any)",
        "City/Town",
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ]
    current = make_result(current_columns, "Unused Column")
    current["records"] = [
        {
            "project_id": "P-001",
            "City/Town": "Boston",
            "Fuel Type (Solar, Wind, etc)": "Solar",
            "Date Application Received": "2026-01-15",
        },
        {
            "project_id": "P-002",
            "City/Town": "Salem",
            "Fuel Type (Solar, Wind, etc)": "Solar",
            "Date Application Received": "2026-01-20",
        },
    ]

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "NEEDS_REVIEW"

def test_changed_values_for_most_projects_need_review():
    columns = ["Facility ID (if any)", *REQUIRED_COLUMNS]
    baseline = make_result(columns, REQUIRED_COLUMNS[1])
    current = make_result(columns, REQUIRED_COLUMNS[1])

    # Three of four comparable values differ: 75%.
    baseline["records"].extend([
        {
            "project_id": "P-003",
            "City/Town": "Lowell",
            REQUIRED_COLUMNS[1]: 300,
            "Fuel Type (Solar, Wind, etc)": "Solar",
            "Date Application Received": "2026-01-22",
        },
        {
            "project_id": "P-004",
            "City/Town": "Worcester",
            REQUIRED_COLUMNS[1]: 400,
            "Fuel Type (Solar, Wind, etc)": "Solar",
            "Date Application Received": "2026-01-25",
        },
    ])
    current["records"].extend([
        {
            "project_id": "P-003",
            "City/Town": "Lowell",
            REQUIRED_COLUMNS[1]: 900,
            "Fuel Type (Solar, Wind, etc)": "Solar",
            "Date Application Received": "2026-01-22",
        },
        {
            "project_id": "P-004",
            "City/Town": "Worcester",
            REQUIRED_COLUMNS[1]: 800,
            "Fuel Type (Solar, Wind, etc)": "Solar",
            "Date Application Received": "2026-01-25",
        },
    ])

    # Alter the first two records as well, making all four values differ.
    current["records"][0][REQUIRED_COLUMNS[1]] = 999
    current["records"][1][REQUIRED_COLUMNS[1]] = 888

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "NEEDS_REVIEW"
    assert result["changes"][0]["type"] == "VALUES_CHANGED"


def test_changed_value_fraction_ignores_new_projects():
    baseline = [
        {"project_id": "P-001", "Capacity": 100},
        {"project_id": "P-002", "Capacity": 200},
    ]
    current = [
        {"project_id": "P-001", "Capacity": 100},
        {"project_id": "P-002", "Capacity": 200},
        {"project_id": "P-003", "Capacity": 300},
    ]

    assert changed_value_fraction(
        baseline,
        current,
        "Capacity",
    ) == 0.0


def test_changed_value_fraction_returns_none_without_matching_projects():
    baseline = [{"project_id": "P-001", "Capacity": 100}]
    current = [{"project_id": "P-002", "Capacity": 100}]

    assert changed_value_fraction(
        baseline,
        current,
        "Capacity",
    ) is None

def test_review_result_does_not_modify_baseline():
    import copy

    columns = ["Facility ID (if any)", *REQUIRED_COLUMNS]
    baseline = make_result(columns, REQUIRED_COLUMNS[1])
    current = make_result(columns, REQUIRED_COLUMNS[1])

    # Simulate a suspicious capacity change.
    current["records"][0][REQUIRED_COLUMNS[1]] = 999
    current["records"][1][REQUIRED_COLUMNS[1]] = 888

    original_baseline = copy.deepcopy(baseline)

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "NEEDS_REVIEW"
    assert baseline == original_baseline

def test_safe_rename_does_not_hide_other_column_value_changes():
    old_capacity = "Design Capacity (Nameplate) (kW)"
    new_capacity = "Nameplate Design Capacity (kW)"

    baseline_columns = ["Facility ID (if any)", *REQUIRED_COLUMNS]
    current_columns = [
        "Facility ID (if any)",
        "City/Town",
        new_capacity,
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ]

    baseline = make_result(baseline_columns, old_capacity)
    current = make_result(current_columns, new_capacity)

    # The capacity rename is safe, but another required column has changed.
    current["records"][0]["City/Town"] = "Different City"
    current["records"][1]["City/Town"] = "Another City"

    result = compare_schema(baseline, current, REQUIRED_COLUMNS)

    assert result["status"] == "NEEDS_REVIEW"