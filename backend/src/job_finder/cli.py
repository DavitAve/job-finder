from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from job_finder.crawler import CrawlSettings
from job_finder.excel import (
    read_companies_from_xlsx,
    sample_companies,
    write_companies,
)
from job_finder.service import CrawlBusyError, CrawlService
from job_finder.database import DatabaseStore
from job_finder.settings import AppSettings, BACKEND_ROOT


DEFAULTS = AppSettings.from_env()


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Collect frontend vacancies from company career pages.",
)


@app.command("import-xlsx")
def import_xlsx(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(
        BACKEND_ROOT / "data" / "companies.json",
        "--output",
        "-o",
        help="Full companies JSON.",
    ),
    sample_output: Path = typer.Option(
        BACKEND_ROOT / "data" / "companies.sample.json",
        "--sample-output",
        help="Fifteen-company MVP sample JSON.",
    ),
) -> None:
    """Convert the source Excel workbook to crawler configuration JSON."""
    try:
        companies = read_companies_from_xlsx(source)
        write_companies(output, companies)
    except (OSError, ValueError) as exc:
        typer.secho(f"Import failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Wrote {len(companies)} companies to {output}")
    try:
        sample = sample_companies(companies)
        write_companies(sample_output, sample)
    except (OSError, ValueError) as exc:
        typer.secho(
            f"Sample file was not updated: {exc}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    else:
        typer.echo(f"Wrote {len(sample)} sample companies to {sample_output}")


@app.command()
def crawl(
    companies_path: Path = typer.Option(
        DEFAULTS.companies_path,
        "--companies",
        "-c",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Companies configuration JSON.",
    ),
    output_directory: Path = typer.Option(
        DEFAULTS.output_directory, "--output-dir", "-o", help="Result directory."
    ),
    concurrency: int = typer.Option(8, min=1, max=50),
    per_domain: int = typer.Option(2, min=1, max=5),
    request_timeout: float = typer.Option(10.0, min=1.0, max=120.0),
    company_timeout: float = typer.Option(60.0, min=5.0, max=600.0),
    browser_pool_wait: float = typer.Option(
        30.0,
        "--browser-pool-wait",
        min=1.0,
        max=120.0,
        help="Maximum wait for a free Playwright page.",
    ),
    retries: int = typer.Option(2, min=0, max=5),
    browser: bool = typer.Option(
        True, "--browser/--no-browser", help="Use Playwright as the final fallback."
    ),
    respect_robots: bool = typer.Option(
        True,
        "--respect-robots/--ignore-robots",
        help="Honor robots.txt rules (enabled by default).",
    ),
) -> None:
    """Crawl enabled companies and commit the result to the configured database."""
    try:
        settings = CrawlSettings(
            concurrency=concurrency,
            per_domain=per_domain,
            request_timeout_seconds=request_timeout,
            company_timeout_seconds=company_timeout,
            browser_pool_wait_seconds=browser_pool_wait,
            retries=retries,
            browser_enabled=browser,
            respect_robots=respect_robots,
        )
        database_url = DEFAULTS.database_url or f"sqlite:///{(output_directory.resolve() / 'job_finder.db').as_posix()}"
        database = DatabaseStore(database_url)
        database.bootstrap_legacy(companies_path, output_directory)
        service = CrawlService(companies_path, output_directory, database=database)
        report = asyncio.run(service.run(settings))
        latest = output_directory / "latest.json"
        snapshot = output_directory / "runs" / f"{report.run_id}.json"
    except KeyboardInterrupt as exc:
        typer.secho("Crawl interrupted; resources were closed.", fg=typer.colors.YELLOW)
        raise typer.Exit(130) from exc
    except CrawlBusyError as exc:
        typer.secho("Crawl failed: another crawl is already running.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except (OSError, ValueError) as exc:
        typer.secho(f"Crawl failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    stats = report.stats
    typer.echo(
        f"Finished: {stats.jobs_found} jobs; "
        f"success={stats.success}, no_jobs={stats.no_jobs}, "
        f"unsupported={stats.unsupported}, unverified={stats.unverified}, "
        f"blocked={stats.blocked}, failed={stats.failed}, skipped={stats.skipped}"
    )
    typer.echo(f"Latest: {latest}")
    typer.echo(f"Snapshot: {snapshot}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="API bind address."),
    port: int = typer.Option(8000, min=1, max=65535),
    reload: bool = typer.Option(False, "--reload", help="Reload on backend code changes."),
) -> None:
    """Run the local HTTP API used by the React application."""
    import uvicorn

    uvicorn.run("job_finder.api:app", host=host, port=port, reload=reload, workers=1)


@app.command("db-upgrade")
def db_upgrade() -> None:
    """Apply all database schema migrations."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(BACKEND_ROOT / "src"))
    config.set_main_option("sqlalchemy.url", DEFAULTS.resolved_database_url)
    command.upgrade(config, "head")
    typer.echo("Database schema is up to date.")


@app.command("db-info")
def db_info() -> None:
    """Show the active local database and imported record counts."""
    database = DatabaseStore(DEFAULTS.resolved_database_url)
    database.bootstrap_legacy(DEFAULTS.companies_path, DEFAULTS.output_directory)
    latest = database.read_latest()
    typer.echo(f"Database: {DEFAULTS.resolved_database_url}")
    typer.echo(f"Companies: {len(database.list_companies())}")
    typer.echo(f"Latest run: {latest.run_id if latest else 'none'}")
    typer.echo(f"Latest jobs: {len(latest.jobs) if latest else 0}")
