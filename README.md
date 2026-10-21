# Hotel booking analysis

Business Analyst Technical Assessment, Set A: data-quality analysis, cancellation diagnostics, normalized SQL, PDF generation, and an Open-Meteo weather enrichment command-line project.

## Status

The attached analysis, SQL, and weather source files are preserved as supplied. Before this upload, the analysis and offline validation tests were rerun successfully against the original workbook in an isolated workspace, including independent pandas checks of both SQL outputs and weather merge tests.

**Section 4 remains incomplete:** the original live weather retrieval failed, and this upload does not claim a successful live API run or verified weather-derived insight. This repository contains source code, not a hosted web app.

## Repository layout

- `code/analysis.py`: cleaning, cancellation analysis, SQLite loading and queries, supporting tables, and `Answer_Report.pdf` generation.
- `code/schema.sql`: normalized SQLite schema and constraints.
- `code/queries.sql`: `RANK()` revenue query and `LAG()` customer-gap query.
- `code/tests.py`: dataset-specific analysis and offline weather checks.
- `project/weather_analyzer.py`: historical weather retrieval, retries, caching, city/date merge validation, and descriptive insights.
- `project/README.md`: the original six-line mini-project README.
- `requirements.txt`: Python dependencies.
- `data/README.md`: local input setup.

## Local setup

Use Python 3.10 or later, preferably in a virtual environment. From the repository root:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell alternative:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Place your original `hotel_bookings.xlsx` in `data/` before running the analysis. The script intentionally validates the supplied assessment workbook's 12,000-row, 28-column contract; it is not a generic importer for arbitrary hotel datasets.

```bash
python code/analysis.py
python code/tests.py
python project/weather_analyzer.py --self-test
python project/weather_analyzer.py
```

`analysis.py` generates the answer PDF at the root and analysis outputs in `results/`. `tests.py` requires those generated outputs. The weather self-test can run without the workbook or network. The live weather command requires cleaned analysis outputs and working internet; it writes diagnostics and insights to `project/output/`. Use `--cache-only` to prohibit network calls and reuse a locally available cache.

## Data protection

The workbook, assessment PDF, answer PDF, generated row-level results, weather outputs/cache, original ZIP manifest, and failed-call log are intentionally not uploaded. `.gitignore` excludes local data, generated reports/results, caches, and common secret files. The original package manifest is not a checksum manifest for this source-only repository.

The original analysis source retains package-oriented report wording such as inputs being bundled and historical build-time weather status. Inputs are **not** bundled in this repository. After a successful future weather run, review `project/output/status.json` and `insight.md` and update the submission report separately; the report generator does not automatically incorporate a later weather result.

## Analytical conventions

Preserve the literal loyalty tier `None`. Cancellation means `Cancelled`, not `No-Show`; realized revenue uses `Completed` bookings. Use check-in month and `property_id` identity. Monetary mismatches remain flagged pending reconciliation. Policy efficacy ranges are assumptions, not causal estimates. Observed check-in weather cannot establish cancellation causation without cancellation timing and other supporting evidence.
