import json

from openpyxl import Workbook
from typer.testing import CliRunner

from job_finder.cli import app
from job_finder.excel import REQUIRED_COLUMNS


def test_import_writes_full_file_when_legacy_sample_companies_are_missing(tmp_path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    company_header = next(
        header for header in REQUIRED_COLUMNS if header not in {"Website", "Careers / Jobs"}
    )
    sheet.append([company_header, "Website", "Careers / Jobs"])
    sheet.append(["New Company", "https://new-company.example", None])
    source = tmp_path / "companies.xlsx"
    output = tmp_path / "companies.json"
    sample_output = tmp_path / "sample.json"
    workbook.save(source)

    result = CliRunner().invoke(
        app,
        [
            "import-xlsx",
            str(source),
            "--output",
            str(output),
            "--sample-output",
            str(sample_output),
        ],
    )

    assert result.exit_code == 0
    assert len(json.loads(output.read_text("utf-8"))) == 1
    assert not sample_output.exists()
    assert "Sample file was not updated" in result.output
