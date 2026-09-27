# Fundamental PIT Audit

Status: **PASS_WITH_LIMITATIONS**

Scope: PIT-bearing fundamental datasets only. Checks logical-key uniqueness, temporal completeness, and the dataset-specific availability rule used by the source builder.

| Dataset | Rows | Numeric-ID rows | Key-null | Duplicate logical keys | date null | available_date null | avail < date | avail = date | avail > date | Rule failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| financials | 1,408,596 | 1,408,596 | 0 | 0 | 0 | 0 | 0 | 0 | 1,408,596 | 0 |
| month_revenue | 267,093 | 267,093 | 0 | 0 | 0 | 0 | 0 | 0 | 267,093 | 0 |
| margin | 4,856,840 | 4,856,840 | 0 | 0 | 0 | 0 | 0 | 4,856,840 | 0 | 0 |
| dividend | 18,557 | 18,557 | 0 | 0 | 0 | 0 | 18,552 | 1 | 4 | 0 |

## Dataset-specific rules

- financials: logical key is (stock_id,date,type); available_date must not precede period date.
- month_revenue: logical key is (stock_id,date); available_date must not precede period date.
- margin: logical key is (stock_id,date); source convention requires available_date = date for T-close -> T+1-open use.
- dividend: available_date is intended to be the announcement/known date and may legitimately precede the ex/event date; ordering is reported but not hard-failed.

Financial rows with blank type: 0.
Dividend rows where available_date = event date: 1; these can include fallback cases and must not automatically be treated as announcement-date evidence.

## Known limitations retained from source semantics

- Financial-statement available dates use statutory deadline approximations; some financial institutions can report later, so financial-stock PIT use needs an additional conservative rule or exclusion.
- Historical financial values may reflect vendor/current revisions rather than the exact originally published figures.
- Dividend rows whose announcement date was unavailable may have fallen back to event date; such rows are not safe as announcement-timing features without explicit provenance.

## Next small task

Freeze the Phase-1 data audit summary and explicit limitations, then move to systematic execution-coordinate replacement without inspecting strategy performance.
