# Design Document: Self-Healing Data Source Watcher

---

## (a) Column Rename Rule and Failure Modes

### Our Rename Rule
To prevent silent schema corruption, our watcher enforces a strict two-stage verification rule before classifying any change as `AUTO_FIXED`:
1. **Syntactic Similarity Filtering**: When a required column is missing, the watcher scans available columns in the new file. We compute normalized string similarity using Python's `SequenceMatcher` combined with base-name extraction that strips parenthetical qualifiers (e.g., `(Solar, Wind, etc)`, `(Nameplate)`, `(kW)`). A candidate must exceed a similarity threshold of $\ge 0.60$ (or match the base name). If multiple candidates tie for top score, the change is deemed ambiguous and flagged as `NEEDS_REVIEW`.
2. **Semantic Value Join on Project ID**: The candidate column is joined against the previous baseline using `project_id` as the primary key. For all common projects ($N_{\text{common}} > 0$), we compare cell values using a type-resilient equality comparator (`values_equal`) that accounts for datetime stringification and numeric formatting (e.g., `10` vs `10.0`).
3. **Threshold Decision**: If $\ge 95\%$ of joined projects have identical values, the column rename is verified safe and classified as `AUTO_FIXED`. The state recipe is updated with the new column name, and a versioned recipe backup is saved. If values diverge ($< 95\%$ match, such as kW being converted to MW, or category changes), the watcher outputs `NEEDS_REVIEW` and leaves recipe and baseline untouched.

### Where the Rule Would Still Get It Wrong
**Permuted or Overhauled Primary Keys**: If a utility upgrades its internal database and issues new project identifier formats in the same month it renames a column (e.g., transforming legacy IDs like `12125` into alphanumeric IDs `MA-UNITIL-2026-001`), the inner join on `project_id` yields zero overlapping keys ($N_{\text{common}} = 0$). Even if the renamed column contains identical data, the rule cannot verify value continuity and conservatively yields `NEEDS_REVIEW` (a false negative). 

Conversely, for a low-cardinality or constant column (e.g., `System Modification Required = 'No'` across 99% of rows), if another boolean column with a similar name appeared, it could pass value matching by coincidence (a potential false positive without additional cross-column entropy checks).

---

## (b) Is Last Month's File "Stale" When This Month's File is Corrupt?

### Definition of "Stale"
In data pipeline engineering, data is defined as **stale** when its elapsed age exceeds the expected refresh frequency (SLO/SLA), meaning downstream models, trading systems, or analysts are operating on out-of-date assumptions rather than current operational reality.

### Architectural Verdict
- **From a Data Integrity Standpoint (Not Stale)**: Last month's baseline represents the last known, verified, and audited state of ground truth. It is not invalid or corrupted. Freezing the baseline and stopping execution (`STOPPED`) preserves data lineage and prevents corrupt records from poisoning downstream lakes.
- **From a Business Operations Standpoint (Stale)**: Interconnection queues are cumulative and time-sensitive. New solar/storage applications arrive every month, capacity ratings are renegotiated, and inactive applications are purged. If August's filing is corrupt, downstream consumers relying on August data lack up-to-date queue positions.
- **Conclusion**: The watcher correctly treats last month's file as **valid for fallback, but stale for operations**. It stops execution (`STOPPED`), locks state, and emits actionable telemetry (`reason: malformed XML token`) to trigger immediate engineering escalation without silently corrupting data.

---

## (c) Two Things in the Real Files That Surprised Us

1. **Actual Corrupt XML in Official Production Data**:
   In `Eversource East (August 2026)` (`interconnection-reports-22/download`), the file is not merely missing fields; its internal `sheet1.xml` contains invalid XML syntax at byte 23,501,450 (`</c<v>21201AJQ...`). Python XML parsers crash with `xml.etree.ElementTree.ParseError`. Real utilities publish malformed files to government portals, demonstrating why full workbook parsing during download validation is mandatory.
2. **Multi-Header Traps and Shifting Metadata Rows**:
   In `Eversource East (March 2026)`, row 2 has an incomplete header (`Facility ID (if any)`, `Design Capacity (Nameplate) (kW)`), followed by an empty row 3, and the true complete header at row 4. A naive scraper looking for the first row containing `Facility ID` would bind to row 2 and miss required columns. Similarly, Unitil moved its header from row 21 (after 20 rows of regulatory disclaimers) in January/February to row 1 in March, requiring dynamic candidate scoring rather than static row offsets.

---

## (d) How AI Was Used and Where It Was Wrong

### How AI Was Used
AI assisted in rapid exploratory analysis: generating regular expressions for parsing unstructured HTML anchor text, formulating parametrized test cases for edge scenarios (e.g., kW to MW conversions), and structuring clean, modular data engineering patterns (atomic file writes, throttled HTTP sessions, and SHA-256 state tracking).

### One Place AI Was Wrong
AI initially implemented value matching by requiring **strict set equality** on project IDs:
```python
# Flawed initial logic proposed by AI:
if old_values.keys() != new_values.keys():
    return False
```
In real interconnection queues, project IDs are **never** identical month-over-month. Utilities add new project applications every single month (e.g., Unitil grew from 1,313 to 1,328 to 1,351 projects), while completed or canceled projects occasionally drop off. Strict set equality caused the column rename check to fail every single month with real data. We corrected this to perform an inner join on common IDs (`set(old) & set(new)`) and evaluate the value agreement ratio across the overlapping subset.
