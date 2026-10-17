# Replay Log: January – August 2026

This document records the results of replaying the Self-Healing Data Source Watcher sequentially across all 16 monthly filings (2 utilities × 8 months) against live filings published on [Mass.gov Distributed Generation Interconnection](https://www.mass.gov/info-details/utility-interconnection-in-massachusetts).

---

## Unitil Replay

| Month | Status | Header Row | Projects | Explanation |
| :--- | :--- | :---: | :---: | :--- |
| **2026-01** | `OK` | 21 | 1,313 | Initial filing; header detected at row 21 after metadata rows; established initial baseline. |
| **2026-02** | `OK` | 21 | 1,328 | Clean incremental update (+15 projects); all required columns and values matched baseline. |
| **2026-03** | `AUTO_FIXED` | 1 | 1,351 | Header shifted to row 1; 'Fuel Type (Solar, Wind, etc)' was renamed to 'Fuel Type'; auto-applied after verifying 100% value match across 1,328 joined projects and saved new recipe version. |
| **2026-04** | `OK` | 1 | 1,366 | Header at row 1; verified cleanly against baseline under updated recipe schema. |
| **2026-05** | `OK` | 1 | 1,381 | Header at row 1; clean monthly filing (+15 projects); values matched baseline. |
| **2026-06** | `OK` | 1 | 1,396 | Header at row 1; clean monthly filing (+15 projects); values matched baseline. |
| **2026-07** | `OK` | 1 | 1,406 | Header at row 1; clean monthly filing (+10 projects); values matched baseline. |
| **2026-08** | `OK` | 1 | 1,431 | Header at row 1; clean monthly filing (+25 projects); values matched baseline. |

---

## Eversource East Replay

| Month | Status | Header Row | Projects | Explanation |
| :--- | :--- | :---: | :---: | :--- |
| **2026-01** | `OK` | 1 | 7,260 | Initial filing; header detected at row 1 (ignoring sub-header row 2); established initial baseline. |
| **2026-02** | `OK` | 1 | 6,989 | Normal queue cleanup (3.7% drop, well within 30% safety threshold); values matched baseline. |
| **2026-03** | `OK` | 4 | 6,989 | Dynamic header scoring rejected partial header at row 2 and correctly selected complete table at row 4; values matched baseline. |
| **2026-04** | `NEEDS_REVIEW` | 1 | 7,045 | Required column kept its name but 58.1% of projects had values changed from 'PV' to 'Solar'; flagged for human review without altering recipe or baseline. |
| **2026-05** | `NEEDS_REVIEW` | 1 | 7,083 | Evaluated against last good baseline (2026-03); values still differ for 58.3% of projects; baseline remains locked. |
| **2026-06** | `NEEDS_REVIEW` | 1 | 7,104 | Evaluated against last good baseline (2026-03); values still differ for 58.5% of projects; baseline remains locked. |
| **2026-07** | `NEEDS_REVIEW` | 1 | 7,115 | Evaluated against last good baseline (2026-03); values still differ for 58.6% of projects; baseline remains locked. |
| **2026-08** | `STOPPED` | — | 0 | File published by utility is corrupted (malformed XML token at byte 23,501,450 inside `sheet1.xml`); safely stopped to protect downstream pipeline. |
