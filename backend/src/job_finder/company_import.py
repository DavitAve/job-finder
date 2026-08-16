from __future__ import annotations

import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field

from job_finder.company_store import CompanyStoreBusyError, mutate_companies
from job_finder.excel import load_companies, read_companies_from_xlsx
from job_finder.models import Company


MAX_XLSX_BYTES = 10 * 1024 * 1024


class CompanyImportBusyError(RuntimeError):
    pass


class CompanyImportResult(BaseModel):
    uploaded: int
    added: int
    duplicates_skipped: int
    total: int
    replaced_existing: bool
    backup_file: str


class CompanyImportPreview(BaseModel):
    uploaded: int
    would_add: int
    duplicates_found: int
    current_total: int
    total_after_import: int
    replaced_existing: bool
    validation_errors: list[str] = Field(default_factory=list)


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", "", normalized)


def _website_key(company: Company) -> str:
    parts = urlsplit(str(company.website_url))
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return host


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}-{suffix}" in used:
        suffix += 1
    value = f"{base}-{suffix}"
    used.add(value)
    return value


def merge_companies(
    existing: list[Company],
    uploaded: list[Company],
    *,
    reset_existing: bool,
    deduplicate: bool,
) -> tuple[list[Company], int, int]:
    merged = [] if reset_existing else list(existing)
    used_ids = {company.id for company in merged}
    known_names = {_name_key(company.name) for company in merged}
    known_websites = {_website_key(company) for company in merged}
    added = 0
    skipped = 0
    for company in uploaded:
        name_key = _name_key(company.name)
        website_key = _website_key(company)
        if deduplicate and (name_key in known_names or website_key in known_websites):
            skipped += 1
            continue
        company_id = _unique_id(company.id, used_ids)
        merged.append(company.model_copy(update={"id": company_id}))
        known_names.add(name_key)
        known_websites.add(website_key)
        added += 1
    return merged, added, skipped


def import_companies_xlsx(
    content: bytes,
    *,
    companies_path: Path,
    output_directory: Path,
    reset_existing: bool = False,
    deduplicate: bool = True,
) -> CompanyImportResult:
    if not content:
        raise ValueError("The uploaded XLSX file is empty")
    if len(content) > MAX_XLSX_BYTES:
        raise ValueError(f"The uploaded XLSX file exceeds {MAX_XLSX_BYTES // 1024 // 1024} MB")
    companies_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".xlsx", dir=companies_path.parent, delete=False
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        try:
            uploaded = read_companies_from_xlsx(temporary_path)
        except (BadZipFile, InvalidFileException) as exc:
            raise ValueError("The uploaded file is not a valid XLSX workbook") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    if not uploaded:
        raise ValueError("The uploaded XLSX file contains no companies")

    try:
        counts: dict[str, int] = {}

        def mutation(existing: list[Company]) -> list[Company]:
            merged, added, skipped = merge_companies(
                existing,
                uploaded,
                reset_existing=reset_existing,
                deduplicate=deduplicate,
            )
            counts.update(added=added, skipped=skipped)
            return merged

        merged, backup_path = mutate_companies(
            companies_path, output_directory, mutation
        )
    except CompanyStoreBusyError as exc:
        raise CompanyImportBusyError(str(exc)) from exc
    return CompanyImportResult(
        uploaded=len(uploaded),
        added=counts["added"],
        duplicates_skipped=counts["skipped"],
        total=len(merged),
        replaced_existing=reset_existing,
        backup_file=str(backup_path),
    )


def preview_companies_xlsx(
    content: bytes,
    *,
    companies_path: Path,
    reset_existing: bool = False,
    deduplicate: bool = True,
) -> CompanyImportPreview:
    if not content:
        raise ValueError("The uploaded XLSX file is empty")
    if len(content) > MAX_XLSX_BYTES:
        raise ValueError(f"The uploaded XLSX file exceeds {MAX_XLSX_BYTES // 1024 // 1024} MB")
    companies_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", dir=companies_path.parent, delete=False) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        try:
            uploaded = read_companies_from_xlsx(temporary_path)
        except (BadZipFile, InvalidFileException) as exc:
            raise ValueError("The uploaded file is not a valid XLSX workbook") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    if not uploaded:
        raise ValueError("The uploaded XLSX file contains no companies")
    existing = load_companies(companies_path) if companies_path.exists() else []
    merged, added, skipped = merge_companies(
        existing,
        uploaded,
        reset_existing=reset_existing,
        deduplicate=deduplicate,
    )
    return CompanyImportPreview(
        uploaded=len(uploaded),
        would_add=added,
        duplicates_found=skipped,
        current_total=len(existing),
        total_after_import=len(merged),
        replaced_existing=reset_existing,
    )
