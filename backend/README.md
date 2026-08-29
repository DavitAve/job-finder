# Frontend Job Finder backend

Python 3.12+ backend for crawling company career pages and serving crawl reports
to the local React application. Python 3.13 is supported.

```powershell
py -V:3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m job_finder db-upgrade
python -m job_finder serve
```

The API binds to `127.0.0.1:8000` by default. A crawl can be started with
`POST /api/crawls`; only one CLI or API crawl may run at a time.

SQLite at `output/job_finder.db` is the source of truth. On first start the
legacy company list, run snapshots, and resume index are imported automatically.
The SQLAlchemy schema is user-scoped and managed by Alembic. Set `DATABASE_URL`
to override the database; the same repository supports a later PostgreSQL move.

Authentication is enabled by default when settings are loaded from the
environment. Passwords use Argon2 and random session tokens are stored only as
SHA-256 hashes; the browser receives the raw token in an HttpOnly, SameSite=Lax
cookie. The first registration claims the legacy `local` user's imported data.
Set `JOB_FINDER_SESSION_DAYS` to change the 30-day lifetime and enable
`JOB_FINDER_SECURE_COOKIES=1` only behind HTTPS.

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

Generic career pages support bounded same-domain pagination through `rel=next`,
labelled Next controls, and numeric pagers. The Playwright fallback additionally
expands Load more controls and bounded infinite scroll. Pagination stops on URL
or content loops, after 20 pages, 20 browser interactions, or 500 raw jobs, and
records limit/fetch problems in the company warnings.

Configuration can be overridden with `JOB_FINDER_COMPANIES_FILE`,
`JOB_FINDER_OUTPUT_DIR`, `JOB_FINDER_CONCURRENCY`, and
`JOB_FINDER_ALLOWED_ORIGINS` (comma-separated). `JOB_FINDER_REFRESH_AFTER_HOURS`
controls the stale-company refresh interval and defaults to 24 hours. Use
`POST /api/crawls` with `{"scope":"stale"}` to crawl only enabled companies
whose `last_crawled_at` is missing or older than that interval.
