from io import BytesIO
from pathlib import Path

from filelock import FileLock
from openpyxl import Workbook
import pytest

from job_finder.company_import import CompanyImportBusyError, import_companies_xlsx
from job_finder.excel import REQUIRED_COLUMNS, load_companies, write_companies
from job_finder.models import Company


def workbook_bytes(rows: list[tuple[str, str]]) -> bytes:
    company_header = next(
        header for header in REQUIRED_COLUMNS if header not in {"Website", "Careers / Jobs"}
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([company_header, "Website", "Careers / Jobs"])
    for name, website in rows:
        sheet.append([name, website, None])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def existing_company() -> Company:
    return Company(id="acme", name="Acme", website_url="https://acme.example")


def test_import_merges_and_deduplicates_against_existing_companies(tmp_path) -> None:
    companies_path = tmp_path / "data" / "companies.json"
    write_companies(companies_path, [existing_company()])

    result = import_companies_xlsx(
        workbook_bytes([
            (" ACME ", "https://duplicate.example"),
            ("New Company", "https://new.example"),
        ]),
        companies_path=companies_path,
        output_directory=tmp_path / "output",
        deduplicate=True,
    )

    assert (result.uploaded, result.added, result.duplicates_skipped, result.total) == (2, 1, 1, 2)
    assert [company.name for company in load_companies(companies_path)] == ["Acme", "New Company"]
    assert Path(result.backup_file).exists()


def test_import_can_keep_duplicates_with_unique_technical_ids(tmp_path) -> None:
    companies_path = tmp_path / "data" / "companies.json"
    write_companies(companies_path, [existing_company()])

    result = import_companies_xlsx(
        workbook_bytes([("Acme", "https://acme.example")]),
        companies_path=companies_path,
        output_directory=tmp_path / "output",
        deduplicate=False,
    )

    companies = load_companies(companies_path)
    assert result.added == 1
    assert [company.id for company in companies] == ["acme", "acme-2"]


def test_reset_replaces_existing_companies_and_import_respects_crawl_lock(tmp_path) -> None:
    companies_path = tmp_path / "data" / "companies.json"
    output_directory = tmp_path / "output"
    write_companies(companies_path, [existing_company()])
    result = import_companies_xlsx(
        workbook_bytes([("Replacement", "https://replacement.example")]),
        companies_path=companies_path,
        output_directory=output_directory,
        reset_existing=True,
    )
    assert result.replaced_existing is True
    assert [company.name for company in load_companies(companies_path)] == ["Replacement"]

    lock = FileLock(str(output_directory / "crawl.lock"))
    with lock, pytest.raises(CompanyImportBusyError):
        import_companies_xlsx(
            workbook_bytes([("Blocked", "https://blocked.example")]),
            companies_path=companies_path,
            output_directory=output_directory,
        )
