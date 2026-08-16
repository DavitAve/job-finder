from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout as FileLockTimeout

from job_finder.excel import load_companies, write_companies
from job_finder.models import Company


class CompanyStoreBusyError(RuntimeError):
    pass


def backup_companies(companies_path: Path) -> Path:
    backups = companies_path.parent / "import-backups"
    backups.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backups / f"companies-{timestamp}.json"
    if companies_path.exists():
        shutil.copy2(companies_path, backup_path)
    else:
        backup_path.write_text("[]\n", encoding="utf-8")
    return backup_path


def mutate_companies(
    companies_path: Path,
    output_directory: Path,
    mutation: Callable[[list[Company]], list[Company]],
) -> tuple[list[Company], Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(output_directory / "crawl.lock"))
    try:
        lock.acquire(timeout=0)
    except FileLockTimeout as exc:
        raise CompanyStoreBusyError("Cannot change companies while a crawl is running") from exc
    try:
        existing = load_companies(companies_path) if companies_path.exists() else []
        updated = mutation(existing)
        if not updated:
            raise ValueError("The companies list cannot be empty")
        backup_path = backup_companies(companies_path)
        write_companies(companies_path, updated)
        return updated, backup_path
    finally:
        lock.release()
