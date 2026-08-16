from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from job_finder.models import Company


SAMPLE_COMPANIES = (
    "EPAM Systems",
    "N-iX",
    "SoftConstruct",
    "Digitain",
    "Picsart",
    "CodeSignal",
    "ServiceTitan",
    "Workato",
    "Synopsys Armenia",
    "NVIDIA Armenia",
    "Cisco Armenia",
    "Krisp",
    "10Web",
    "Sololearn",
    "EasyDMARC",
)

REQUIRED_COLUMNS = {"Компания", "Website", "Careers / Jobs"}

# Verified public career boards that supersede stale landing-page URLs in the workbook.
CAREERS_URL_OVERRIDES = {
    "EPAM Systems": "https://careers.epam.com/en/jobs/armenia",
    "SoftConstruct": "https://staff.am/company/softconstruct",
    "Picsart": "https://picsart.com/careers/jobs",
    "CodeSignal": "https://jobs.gem.com/codesignal/",
    "Digitain": "https://staff.am/company/digitain",
    "Cisco Armenia": "https://careers.cisco.com/global/en/search-results",
    "10Web": "https://jobs.10web.io/",
    "Sololearn": "https://www.sololearn.com/en/career",
    "Zeptolab": "https://apply.workable.com/zeptolab/",
}

ADAPTER_OPTIONS_OVERRIDES = {
    "Picsart": {"ats": {"kind": "greenhouse", "token": "picsart"}},
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or "company"


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def read_companies_from_xlsx(path: Path) -> list[Company]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        try:
            raw_headers = next(rows)
        except StopIteration as exc:
            raise ValueError("The Excel file is empty") from exc

        headers = [_string(value) for value in raw_headers]
        missing = REQUIRED_COLUMNS.difference(headers)
        if missing:
            raise ValueError(f"Missing required Excel columns: {', '.join(sorted(missing))}")
        indexes = {header: index for index, header in enumerate(headers)}

        companies: list[Company] = []
        used_ids: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            name = _string(row[indexes["Компания"]])
            website = _string(row[indexes["Website"]])
            careers = _string(row[indexes["Careers / Jobs"]])
            original_careers = careers
            careers = CAREERS_URL_OVERRIDES.get(name, careers)
            if not name and not website and not careers:
                continue
            if not name or not website:
                raise ValueError(
                    f"Row {row_number} must contain company and website URL"
                )
            base_id = slugify(name)
            company_id = base_id
            suffix = 2
            while company_id in used_ids:
                company_id = f"{base_id}-{suffix}"
                suffix += 1
            used_ids.add(company_id)

            metadata: dict[str, str] = {}
            for header in (
                "Тип",
                "Страна / основные локации",
                "Русскоязычность",
                "Remote из Армении",
                "Frontend compatibility",
                "Почему подходит",
                "LinkedIn",
            ):
                if header in indexes:
                    value = _string(row[indexes[header]])
                    if value:
                        metadata[header] = value
            if original_careers and careers != original_careers:
                metadata["Original Careers / Jobs"] = original_careers

            companies.append(
                Company(
                    id=company_id,
                    name=name,
                    website_url=website,
                    careers_url=careers or None,
                    adapter_options=ADAPTER_OPTIONS_OVERRIDES.get(name, {}),
                    metadata=metadata,
                )
            )
        return companies
    finally:
        workbook.close()


def sample_companies(companies: list[Company]) -> list[Company]:
    by_name = {company.name.casefold(): company for company in companies}
    missing = [name for name in SAMPLE_COMPANIES if name.casefold() not in by_name]
    if missing:
        raise ValueError(f"Sample companies missing from Excel: {', '.join(missing)}")
    return [by_name[name.casefold()] for name in SAMPLE_COMPANIES]


def write_companies(path: Path, companies: list[Company]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [company.model_dump(mode="json") for company in companies]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_companies(path: Path) -> list[Company]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("companies")
    if not isinstance(payload, list):
        raise ValueError("Companies JSON must be an array or contain a 'companies' array")
    return [Company.model_validate(item) for item in payload]
