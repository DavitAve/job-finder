# Frontend Job Finder backend

Python 3.12+ backend for crawling company career pages and serving crawl reports
to the local React application. Python 3.13 is supported.

```powershell
py -V:3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m job_finder serve
```

The API binds to `127.0.0.1:8000` by default. A crawl can be started with
`POST /api/crawls`; only one CLI or API crawl may run at a time.

If a configured careers URL fails or redirects to the company homepage, the
crawler performs a bounded fallback discovery from `website_url`. It follows
only same-company links and links to known ATS providers, tries at most five
candidates, and records the actual URL in `resolved_careers_url`. Suggestions
are written to `output/discovered-careers.json`; the source companies file is
never changed automatically.

`careers_url` is optional in JSON and the Excel cell may be empty. In that case
discovery starts directly from `website_url` (with a browser fallback for
JavaScript navigation). Custom "Page not found" pages that return HTTP 200 are
treated like regular 404 responses and also trigger discovery.

Configuration can be overridden with `JOB_FINDER_COMPANIES_FILE`,
`JOB_FINDER_OUTPUT_DIR`, `JOB_FINDER_CONCURRENCY`, and
`JOB_FINDER_ALLOWED_ORIGINS` (comma-separated).
