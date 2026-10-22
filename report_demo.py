"""Local synthetic two-CSV reporting demonstration; standard library only."""
import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from hashlib import sha256
from html import escape
import io
import json
import os
from pathlib import Path
import re
import sys

MAX_BYTES, MAX_ROWS = 2 * 1024 * 1024, 10000
HEADERS = {
    "performance": ["date", "campaign_id", "impressions", "clicks", "spend", "currency"],
    "leads": ["date", "campaign_id", "leads"],
}
FORMULAS = {
    "spend": "sum(spend)", "impressions": "sum(impressions)",
    "clicks": "sum(clicks)", "reported_leads": "sum(source-reported leads)",
    "ctr_percent": "clicks / impressions * 100",
    "cost_per_reported_lead": "spend / reported leads",
}
LABELS = ["Total spend (USD)", "Impressions", "Clicks", "Source-reported leads",
          "Click-through rate (%)", "Cost per reported lead (USD)"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_date(value):
    require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value),
            "dates must use exact YYYY-MM-DD")
    return date.fromisoformat(value)


def count(value):
    require(re.fullmatch(r"[0-9]+", value), "counts must be nonnegative decimal integers")
    return int(value)


def money(value):
    require(re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value),
            "spend must be a nonnegative finite decimal with at most two decimal places")
    return Decimal(value)


def read_source(path, kind, periods):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, f"{path.name}: maximum file size is 2 MiB")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    require(next(reader, None) == HEADERS[kind], f"{path.name}: expected header {HEADERS[kind]}")
    rows = {}
    for number, cells in enumerate(reader, 1):
        require(number <= MAX_ROWS, f"{path.name}: maximum is 10000 data rows")
        require(len(cells) == len(HEADERS[kind]), f"{path.name}: wrong cell count at data row {number}")
        day, campaign = parse_date(cells[0]), cells[1]
        require(campaign.strip(), f"{path.name}: campaign_id must be nonempty")
        require(any(start <= day <= end for start, end in periods.values()),
                f"{path.name}: date {day} is outside the two periods")
        key = (day, campaign)
        require(key not in rows, f"{path.name}: duplicate date/campaign key at data row {number}")
        if kind == "performance":
            require(cells[5] == "USD", f"{path.name}: currency must be USD")
            rows[key] = dict(impressions=count(cells[2]), clicks=count(cells[3]), spend=money(cells[4]))
        else:
            rows[key] = dict(reported_leads=count(cells[2]))
    require(rows, f"{path.name}: no data rows")
    return rows, dict(filename=path.name, sha256=sha256(raw).hexdigest(), rows=len(rows))


def decimal_text(value):
    return None if value is None else format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def calculate(performance, leads, periods, sources):
    require(performance.keys() == leads.keys(), "source date/campaign keys must match exactly")
    campaigns = sorted({campaign for day, campaign in performance})
    expected = sum((end - start).days + 1 for start, end in periods.values())
    for campaign in campaigns:
        require(sum(key[1] == campaign for key in performance) == expected,
                "each campaign must include every date in both inclusive periods")
    # Enough decimal precision for exact sums and two-place rendered ratios, even for large inputs.
    digits = max(len(str(value)) for row in performance.values() for value in row.values())
    digits = max(digits, max(len(str(row["reported_leads"])) for row in leads.values()))
    with localcontext() as context:
        context.prec = max(50, digits * 2 + 20)
        results, numeric = {}, {}
        for name, (start, end) in periods.items():
            keys = [key for key in performance if start <= key[0] <= end]
            totals = {metric: sum((performance[key][metric] for key in keys),
                                 Decimal(0) if metric == "spend" else 0)
                      for metric in ("spend", "impressions", "clicks")}
            totals["reported_leads"] = sum(leads[key]["reported_leads"] for key in keys)
            totals["ctr_percent"] = (Decimal(totals["clicks"]) / totals["impressions"] * 100
                                     if totals["impressions"] else None)
            totals["cost_per_reported_lead"] = (totals["spend"] / totals["reported_leads"]
                                                  if totals["reported_leads"] else None)
            numeric[name] = totals
            metrics = {key: decimal_text(value) if isinstance(value, Decimal) or value is None else value
                       for key, value in totals.items()}
            results[name] = dict(start=start.isoformat(), end=end.isoformat(), rows=len(keys), metrics=metrics)
        changes = {}
        for key in FORMULAS:
            before, after = numeric["previous"][key], numeric["current"][key]
            changes[key] = decimal_text((Decimal(after) - before) / before * 100
                                       if before not in (None, 0) and after is not None else None)
    return dict(demonstration="Synthetic demonstration using invented formats and data",
                currency="USD", campaigns=campaigns, sources=sources, periods=results,
                formulas=FORMULAS, percent_changes=changes,
                validation=dict(status="passed", max_file_bytes=MAX_BYTES, max_data_rows=MAX_ROWS,
                                complete_dates=True, unique_matching_keys=True))


def render(receipt):
    def safe(value):
        return escape(str(value), quote=True)

    def display(value):
        return "N/A" if value is None else safe(value)

    previous, current = (receipt["periods"][name] for name in ("previous", "current"))
    rows = "".join(f"<tr><th scope='row'>{label}</th><td>{display(previous['metrics'][key])}</td>"
                   f"<td>{display(current['metrics'][key])}</td><td>{display(receipt['percent_changes'][key])}</td></tr>"
                   for key, label in zip(FORMULAS, LABELS))
    formulas = "".join(f"<li>{label}: <code>{safe(formula)}</code></li>"
                       for label, formula in zip(LABELS, FORMULAS.values()))
    sources = "".join(f"<li>{safe(kind)}: <strong>{safe(source['filename'])}</strong>; "
                      f"{source['rows']} data rows. SHA-256: <code>{source['sha256']}</code></li>"
                      for kind, source in receipt["sources"].items())
    periods = "".join(f"<li>{name.title()}: {period['start']} to {period['end']} inclusive; "
                      f"{period['rows']} joined rows.</li>" for name, period in receipt["periods"].items())
    campaigns = ", ".join(safe(value) for value in receipt["campaigns"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,">
<title>Synthetic demonstration — campaign report</title><style>
body{{font:16px/1.6 system-ui,sans-serif;color:#17212b;background:#f3f5f7;margin:0}}
main{{max-width:960px;margin:auto;padding:28px}}section,header{{background:white;padding:24px;margin-bottom:18px;border:1px solid #ccd3da;border-radius:8px}}
h1,h2{{line-height:1.25}}.notice{{border-left:4px solid #495c78;padding-left:14px}}code{{overflow-wrap:anywhere;font-size:.85em}}
.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{padding:10px;text-align:right;border-bottom:1px solid #ccd3da}}th:first-child{{text-align:left}}li{{overflow-wrap:anywhere}}
@media(max-width:600px){{main{{padding:12px}}section,header{{padding:16px}}th,td{{padding:8px;font-size:14px}}}}
@media print{{body{{background:white;color:black}}main{{max-width:none;padding:0}}section,header{{border:0;padding:10px 0}}tr{{break-inside:avoid}}}}
</style></head><body><main>
<header><p>LOCAL REPORTING PROOF · USD</p><h1>Synthetic demonstration</h1>
<p class="notice">All data is fictional and uses invented formats. This is an engineering example, not a customer result, live integration, or evidence of business improvement.</p>
<p>Campaigns: {campaigns}</p><ul>{periods}</ul></header>
<section><h2>Six illustrative metrics</h2><div class="table-wrap"><table><thead><tr><th scope="col">Metric / total</th>
<th scope="col">Previous</th><th scope="col">Current</th><th scope="col">Relative change (%)</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Relative change = (current − previous) / previous × 100. N/A means a zero baseline or undefined ratio. Rate changes are relative percentages, not percentage-point differences.</p></section>
<section><h2>Definitions and formulas</h2><ul>{formulas}</ul>
<p>Leads are additive source-reported counts, not unique customers or cross-platform attribution. No inferred or missing values are filled. Ratios and changes are rounded to two decimal places using half-up rounding; JSON preserves exact spend totals as decimal strings.</p></section>
<section><h2>Sources and validation</h2><p><strong>Validation passed.</strong> Both files have unique, identical date/campaign keys. Every campaign includes every day in both periods.</p><ul>{sources}</ul>
<p>Limits: UTF-8 CSV; exact headers and cell counts; at most 2 MiB and 10,000 data rows per file; nonnegative integer counts; nonnegative USD amounts with at most two decimal places; valid nonoverlapping inclusive periods. No network calls or external assets.</p>
<p>This validates the file contract, not the truth, attribution, or accounting accuracy of source data. Open this file locally. Use your browser’s Print / Save as PDF for a printable copy; no separate PDF generator is included. <a href="receipt.json">Inspect the calculation receipt and source hashes</a>.</p></section>
</main></body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("performance", "leads", "previous-start", "previous-end", "current-start", "current-end", "output-dir"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    created = False
    try:
        require(not os.path.lexists(output), "output directory already exists; refusing to overwrite")
        periods = {name: (parse_date(getattr(args, name + "_start")), parse_date(getattr(args, name + "_end")))
                   for name in ("previous", "current")}
        require(all(start <= end for start, end in periods.values()), "period ranges cannot be reversed")
        p, c = periods.values()
        require(p[1] < c[0] or c[1] < p[0], "periods cannot overlap")
        performance, performance_source = read_source(Path(args.performance), "performance", periods)
        leads, leads_source = read_source(Path(args.leads), "leads", periods)
        receipt = calculate(performance, leads, periods, dict(performance=performance_source, leads=leads_source))
        html = render(receipt)
        encoded = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        output.mkdir()
        created = True
        (output / "report.html").write_text(html, encoding="utf-8")
        (output / "receipt.json").write_text(encoded, encoding="utf-8")
    except (ValueError, OSError, csv.Error, UnicodeError, InvalidOperation) as error:
        if created:
            for name in ("report.html", "receipt.json"):
                (output / name).unlink(missing_ok=True)
            output.rmdir()
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Created {output / 'report.html'} and {output / 'receipt.json'} (synthetic demonstration).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
