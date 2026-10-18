# Self-Healing Data Source Watcher

A resilient, production-grade Python tool that monitors monthly public utility interconnection filings (Unitil and Eversource East) published on [Mass.gov](https://www.mass.gov/info-details/utility-interconnection-in-massachusetts).

The watcher detects schema shifts, moving header rows, column renames, value drift, duplicate filings, and corrupt files. It automatically heals safe changes (updating recipe state) and halts or flags risky ones before inaccurate data enters downstream data pipelines.

---

## Key Features

- **Automated Link Discovery**: Scrapes Mass.gov landing pages, matching utility names and months despite irregular anchor labels and varying slug patterns.
- **Throttled HTTP & WAF Fallback**: Enforces $\ge 3$ seconds between outbound requests and automatically rotates `User-Agent` headers upon receiving HTTP 403 Forbidden responses.
- **Dynamic Header Detection**: Locates header rows by scoring candidate rows against expected columns rather than relying on brittle, hardcoded row numbers.
- **Self-Healing Schema Updates**: Automatically identifies renamed columns using syntactic similarity ($\ge 60\%$) and verifies that values match ($\ge 95\%$) across common project IDs joined from baseline data. Safe renames update the active recipe in `state/` and generate versioned backups.
- **Safety Thresholds & Guards**:
  - Drops in project count exceeding $30\%$ halt the pipeline (`STOPPED`).
  - Column value changes exceeding $50\%$ on existing columns require human intervention (`NEEDS_REVIEW`).
  - Columns with similar names but different values (e.g. kW converted to MW) are never auto-fixed (`NEEDS_REVIEW`).
  - Malformed XML or non-workbook files are caught during download stream validation (`STOPPED`).
  - Baseline state and recipe files remain strictly immutable during any `NEEDS_REVIEW` or `STOPPED` run.

---

## Installation & Setup

Requirements: **Python 3.9+**

```bash
# 1. Clone repository
git clone https://github.com/Ashish-Bakshi/enerdatics-assignment.git
cd enerdatics-assignment

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Command Line Usage

The tool requires the following command-line interface:

```bash
python watcher.py --recipe recipe.yaml --utility "<Utility Name>" --month <YYYY-MM> --state-dir state/ --report <out.json>
```

### Examples:

```bash
# Unitil January 2026 (Initial Baseline)
python watcher.py --recipe recipe.yaml --utility "Unitil" --month 2026-01 --state-dir state/ --report reports/unitil_2026-01.json

# Unitil March 2026 (Auto-fixed column rename: 'Fuel Type (Solar, Wind, etc)' -> 'Fuel Type')
python watcher.py --recipe recipe.yaml --utility "Unitil" --month 2026-03 --state-dir state/ --report reports/unitil_2026-03.json

# Eversource East April 2026 (Flags NEEDS_REVIEW due to >50% values changed in Fuel Type)
python watcher.py --recipe recipe.yaml --utility "Eversource East" --month 2026-04 --state-dir state/ --report reports/eversource_east_2026-04.json
```

### Exit Codes:
- `0`: Run completed cleanly (`OK`, `NO_NEW_DATA`, or `AUTO_FIXED`).
- `1`: Run flagged or halted (`NEEDS_REVIEW` or `STOPPED`).

---

## Decision Rules & Thresholds

Every run terminates with exactly one status:

| Status | Meaning | State / Recipe Action |
| :--- | :--- | :--- |
| **`OK`** | New data with matching schema and consistent values. | Updates baseline in `state/`. |
| **`NO_NEW_DATA`** | File SHA-256 matches baseline; duplicate file. | State unchanged. |
| **`AUTO_FIXED`** | Safe column rename identified and verified against baseline. | Saves updated recipe version and updates baseline. |
| **`NEEDS_REVIEW`** | Suspicious change (value drift, similar name with different values). | **Changes nothing.** Proposed in report. |
| **`STOPPED`** | Critical failure (corrupt file, missing sheet, $>30\%$ project drop, 404). | **Changes nothing.** Halts pipeline safely. |

### Engineering Thresholds Rationale:
1. **`PROJECT_COUNT_DROP_THRESHOLD = 0.30` (30%)**: Utility interconnection queues are cumulative by regulation; new applications are continuously filed. While minor drops occur due to cleanup of canceled applications (e.g. 3.7% in Eversource East Feb 2026), drops exceeding 30% indicate severe table truncation or broken export filters.
2. **`VALUE_CHANGE_THRESHOLD = 0.50` (50%)**: If a required column keeps its name but $>50\%$ of existing projects have new values, it signals a semantic redefinition (e.g., fuel category recoding from 'PV' to 'Solar') requiring engineering signoff.
3. **`COLUMN_SIMILARITY_THRESHOLD = 0.60` (60%)**: Prevents mapping completely unrelated columns while capturing real spreadsheet variations (e.g., stripping parenthetical units or qualifiers).
4. **`VALUE_MATCH_THRESHOLD = 0.95` (95%)**: A column rename is only safe to auto-apply if at least 95% of common project IDs have matching values, accounting for small monthly revision margins.

---

## Running the Automated Replay

To execute all 16 runs (Unitil and Eversource East from January to August 2026) in order:

```bash
python replay.py --utility all
```

Or for a single utility:
```bash
python replay.py --utility Unitil
```

See [REPLAY.md](REPLAY.md) for the complete run log and [DESIGN.md](DESIGN.md) for architectural discussion.

---

## Running the Test Suite

A comprehensive test suite covers all requirements and failure modes:

```bash
python -m pytest -v
```

### Included Tests :
1. `tests/test_auto_fixed.py`: Tests safe column renames and automatic fixes.
2. `tests/test_baseline.py`: Tests baseline state handling.
3. `tests/test_changed_values.py`: Tests detection of significant value changes.
4. `tests/test_cli.py`: Tests command-line interface behavior.
5. `tests/test_corrupt_file.py`: Tests handling of malformed XML and invalid workbooks.
6. `tests/test_recipe.py`: Tests recipe loading and state handling.
7. `tests/test_replay.py`: Tests replay workflow behavior.
8. `tests/test_safety.py`: Tests safety-related behavior.
9. `tests/test_safety_and_edge_cases.py`: Tests project-count drops, duplicate SHA-256 detection, and HTTP 403 User-Agent rotation.
10. `tests/test_schema.py`: Tests schema comparison and column-rename handling.
11. `tests/test_similar_name_diff_values.py`: Tests similarly named columns with different values.
12. `tests/test_source.py`: Tests source link discovery.
13. `tests/test_source_client.py`: Tests HTTP client behavior, downloads, retries, and caching.
14. `tests/test_workbook.py`: Tests workbook parsing and validation.

Run the complete suite with:

```bash
python -m pytest -v
```

### Live Download Verification

A live smoke test against Mass.gov confirmed that the watcher can fetch the
landing page, discover the Unitil March 2026 report link, download a workbook
into a fresh temporary cache, and validate the workbook.

- **Download:** Successful; workbook size was 664,439 bytes.
- **Workbook validation:** Successful; the workbook opened and its worksheet
  could be read.
- **Fresh-state processing:** Returned `NEEDS_REVIEW` because the starting
  recipe expected `Fuel Type (Solar, Wind, etc)`, while the downloaded workbook
  contained `Fuel Type`. This is the current initial-run behavior when a
  required column is missing and no baseline exists.
- **Existing replay report:** `reports/unitil_2026-03.json` records `AUTO_FIXED`
  for the same workbook hash, with a 100% match rate across 1,328 joined
  projects. This replay result is separate from the fresh-state smoke test.
