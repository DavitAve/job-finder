from pathlib import Path

from openpyxl import Workbook

from job_finder.excel import REQUIRED_COLUMNS, read_companies_from_xlsx


def test_excel_import_preserves_metadata(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Компания", "Website", "Careers / Jobs", "Тип"])
    sheet.append(["Acme", "https://acme.example", "https://acme.example/jobs", "SaaS"])
    source = tmp_path / "companies.xlsx"
    workbook.save(source)

    companies = read_companies_from_xlsx(source)
    assert len(companies) == 1
    assert companies[0].id == "acme"
    assert companies[0].metadata == {"Тип": "SaaS"}


def test_excel_import_applies_verified_careers_url_override(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Компания", "Website", "Careers / Jobs"])
    sheet.append(["10Web", "https://10web.io", "https://10web.io/careers/"])
    source = tmp_path / "companies.xlsx"
    workbook.save(source)

    companies = read_companies_from_xlsx(source)
    assert str(companies[0].careers_url) == "https://jobs.10web.io/"


def test_excel_import_fills_missing_verified_zeptolab_careers_url(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Компания", "Website", "Careers / Jobs"])
    sheet.append(["Zeptolab", "https://zeptolab.com", None])
    source = tmp_path / "companies.xlsx"
    workbook.save(source)

    companies = read_companies_from_xlsx(source)
    assert str(companies[0].careers_url) == "https://apply.workable.com/zeptolab/"
    assert "Original Careers / Jobs" not in companies[0].metadata


def test_excel_import_allows_company_without_careers_url(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    company_header = next(
        header for header in REQUIRED_COLUMNS if header not in {"Website", "Careers / Jobs"}
    )
    sheet.append([company_header, "Website", "Careers / Jobs"])
    sheet.append(["New Company", "https://new-company.example", None])
    source = tmp_path / "companies.xlsx"
    workbook.save(source)

    companies = read_companies_from_xlsx(source)

    assert len(companies) == 1
    assert companies[0].careers_url is None


def test_excel_import_adds_verified_ats_hint(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Компания", "Website", "Careers / Jobs"])
    sheet.append(["Picsart", "https://picsart.com", "https://picsart.com/jobs"])
    source = tmp_path / "companies.xlsx"
    workbook.save(source)

    companies = read_companies_from_xlsx(source)
    assert companies[0].adapter_options == {
        "ats": {"kind": "greenhouse", "token": "picsart"}
    }
