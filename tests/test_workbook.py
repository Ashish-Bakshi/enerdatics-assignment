from openpyxl import Workbook
import pytest

from watcher.workbook import read_workbook


CONFIG = {
    "sheet": "Sheet1",
    "id_column": "Facility ID (if any)",
    "required_columns": [
        "City/Town",
        "Design Capacity (Nameplate) (kW)",
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ],
}


def create_workbook(path, include_headers=True):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"

    sheet.append(["Monthly Interconnection Report"])
    sheet.append(["Published January 2026"])

    if include_headers:
        sheet.append([
            "Facility ID (if any)",
            "City/Town",
            "Design Capacity (Nameplate) (kW)",
            "Fuel Type (Solar, Wind, etc)",
            "Date Application Received",
        ])
        sheet.append([
            "P-001",
            "Boston",
            250,
            "Solar",
            "2026-01-15",
        ])
        sheet.append([
            None,
            "A row without an ID",
            100,
            "Solar",
            "2026-01-16",
        ])

    workbook.save(path)
    workbook.close()


def test_finds_header_after_title_rows(tmp_path):
    path = tmp_path / "report.xlsx"
    create_workbook(path)

    result = read_workbook(path, CONFIG)

    assert result["header_row"] == 3
    assert result["projects"] == 1
    assert result["records"][0]["project_id"] == "P-001"


def test_extracts_required_column_values(tmp_path):
    path = tmp_path / "report.xlsx"
    create_workbook(path)

    result = read_workbook(path, CONFIG)

    record = result["records"][0]

    assert record["City/Town"] == "Boston"
    assert record["Design Capacity (Nameplate) (kW)"] == 250
    assert record["Fuel Type (Solar, Wind, etc)"] == "Solar"


def test_missing_worksheet_raises_error(tmp_path):
    path = tmp_path / "report.xlsx"
    create_workbook(path)

    config = {**CONFIG, "sheet": "Missing Sheet"}

    with pytest.raises(ValueError, match="Worksheet"):
        read_workbook(path, config)


def test_missing_required_headers_raises_error(tmp_path):
    path = tmp_path / "report.xlsx"
    create_workbook(path, include_headers=False)

    with pytest.raises(ValueError, match="Could not find a header row"):
        read_workbook(path, CONFIG)

def test_allow_missing_required_header_reads_available_columns(tmp_path):
    path = tmp_path / "report.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"

    sheet.append(["Monthly Interconnection Report"])
    sheet.append([
        "Facility ID (if any)",
        "City/Town",
        "Nameplate Capacity (kW)",
        "Fuel Type (Solar, Wind, etc)",
        "Date Application Received",
    ])
    sheet.append([
        "P-001",
        "Boston",
        250,
        "Solar",
        "2026-01-15",
    ])

    workbook.save(path)
    workbook.close()

    result = read_workbook(path, CONFIG, allow_missing=True)

    assert result["projects"] == 1
    assert result["records"][0]["project_id"] == "P-001"
    assert result["records"][0]["Nameplate Capacity (kW)"] == 250
    assert "Design Capacity (Nameplate) (kW)" not in result["records"][0]