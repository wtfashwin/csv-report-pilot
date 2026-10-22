# Synthetic reporting proof

A local Python 3.9+ example that validates two invented CSV formats and produces
one standalone HTML comparison plus a JSON calculation receipt. It uses only the
Python standard library. It makes no network calls and needs no account or
dependencies.

All supplied data is fictional. This is an engineering example, not a customer
result, a live connector, or evidence of time saved or business improvement.

[View the synthetic report](https://wtfashwin.github.io/Portfolio/reporting-example/)
or [inspect its calculation receipt](https://wtfashwin.github.io/Portfolio/reporting-example/receipt.json).
The published example uses the supplied fixtures; it does not accept uploads.

## Run the example

From this directory, run the following command. `output-valid` must not already
exist; the tool refuses existing paths rather than overwriting them.

```sh
python3 report_demo.py --performance fixtures/performance.csv --leads fixtures/leads.csv --previous-start 2026-10-05 --previous-end 2026-10-11 --current-start 2026-10-12 --current-end 2026-10-18 --output-dir output-valid
```

Expected exit code: `0`. Open `output-valid/report.html` in a browser. The report
has no JavaScript or external assets. Use the browser's Print / Save as PDF for a
printable copy; this tool does not generate a PDF itself.

The single fictional campaign has these explicitly illustrative totals:

| Metric | Previous: 5–11 Oct 2026 | Current: 12–18 Oct 2026 |
| --- | ---: | ---: |
| Spend (USD) | 280.00 | 315.00 |
| Impressions | 3,500 | 4,200 |
| Clicks | 140 | 210 |
| Source-reported leads | 14 | 21 |
| Click-through rate (%) | 4.00 | 5.00 |
| Cost per reported lead (USD) | 20.00 | 15.00 |

Each source has 14 data rows. The first four metrics are sums. CTR is
`clicks / impressions * 100`; cost per reported lead is `spend / reported leads`.
Leads are additive source-reported counts, not unique customers or cross-platform
attribution. Relative change is `(current - previous) / previous * 100`.
Undefined ratios and changes from a zero baseline display `N/A` (JSON `null`).
Rate changes use relative percentages, not percentage-point differences.

`receipt.json` records the periods, six metrics, formulas, row counts, validation
status and SHA-256 of each source file. It contains basenames and campaign IDs,
not absolute paths or raw rows. Spend totals are exact decimal strings; ratios
and relative changes are rounded half-up to two decimal places. Identical input
bytes, basenames and period arguments produce identical report and receipt bytes.
No current timestamp is inserted.

## See a validation failure

```sh
python3 report_demo.py --performance fixtures/performance.csv --leads fixtures/leads-duplicate.csv --previous-start 2026-10-05 --previous-end 2026-10-11 --current-start 2026-10-12 --current-end 2026-10-18 --output-dir output-invalid
```

Expected exit code: `2`, with `duplicate date/campaign key` on stderr. The invalid
fixture repeats its last key. No `output-invalid` directory or partial report is
created. All validation runs before output creation. Any existing output path,
including an existing report, is refused and preserved.

## File contract and limits

The headers must appear in exactly this order, with exactly these cells:

```text
date,campaign_id,impressions,clicks,spend,currency
date,campaign_id,leads
```

- UTF-8 CSV; maximum 2 MiB and 10,000 data rows per file. Empty files or files
  containing only a header are rejected. Extra or missing headers/cells fail.
- Dates use exact `YYYY-MM-DD`. Periods are inclusive and cannot overlap or have
  an end before their start. All input dates must fall within one of the periods.
- Every campaign must have every date in both periods. Date/campaign keys must
  be unique and identical across the files. No zero filling or extrapolation.
- Campaign IDs must contain non-whitespace text. Their exact text is retained.
- Currency is exactly `USD`. Spend is a nonnegative plain decimal with at most
  two fractional places. Counts use decimal digits only and must be nonnegative
  integers. Negative, nonfinite, fractional-count and scientific-notation values
  fail. Python's CSV and integer parsing limits also apply to individual fields.
- Validation checks this file contract. It cannot establish whether source data
  is true, complete upstream, correctly attributed, or suitable for accounting.

## Check the behavior

```sh
python3 -m unittest -v
python3 -m py_compile report_demo.py
```

Tests cover the fixture calculations and hashes, deterministic output, exact
decimal addition, zero denominators, HTML escaping, malformed data, duplicate and
missing keys/dates, periods, file/row limits and preservation of existing output.
No dependency installation or network access is needed.

## Replace the example only after agreeing the scope

An actual implementation starts with a buyer's redacted reference report, two
representative exports, agreed metric definitions and the desired presentation.
Map the real headers and date/campaign keys explicitly. Confirm currency, period
coverage, how repeated leads should be counted and the buyer's accepted totals
before replacing this invented contract. Keep the validation checks and compare
the result against the accepted reference.

The proposed six-metric paid scope is subject to buyer agreement. This example
does not demonstrate a real platform export, live integration, scheduled service,
customer approval or payment. Keep client files and private campaign records out
of any public repository or sample report; source hashes do not anonymize data.
