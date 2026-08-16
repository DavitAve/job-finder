from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from job_finder.models import CrawlReport


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_report(report: CrawlReport, output_directory: Path) -> tuple[Path, Path]:
    payload = report.model_dump(mode="json")
    snapshot = output_directory / "runs" / f"{report.run_id}.json"
    latest = output_directory / "latest.json"
    _write_json_atomic(snapshot, payload)
    try:
        _write_json_atomic(latest, payload)
    except Exception:
        # A run is committed only when latest points at it. Do not expose an
        # orphan snapshot as history when that final commit fails.
        snapshot.unlink(missing_ok=True)
        raise
    try:
        _prune_snapshots(output_directory / "runs", keep=4)
    except OSError:
        # Retention is housekeeping after the report has committed. A later
        # run can retry it; the completed crawl must not be reported as failed.
        pass
    discoveries = [
        {
            "company_id": company.company_id,
            "company": company.company,
            "configured_careers_url": company.careers_url,
            "resolved_careers_url": company.resolved_careers_url,
        }
        for company in report.companies
        if company.careers_url_discovered and company.resolved_careers_url
    ]
    if discoveries:
        try:
            _write_json_atomic(
                output_directory / "discovered-careers.json",
                {
                    "run_id": report.run_id,
                    "generated_at": report.finished_at.isoformat(),
                    "discoveries": discoveries,
                },
            )
        except OSError:
            # Discovery suggestions are an audit aid and must not invalidate a
            # successfully committed crawl report.
            pass
    return latest, snapshot


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def read_latest(output_directory: Path) -> CrawlReport | None:
    path = output_directory / "latest.json"
    if not path.exists():
        return None
    return CrawlReport.model_validate(_read_json(path))


def read_run(output_directory: Path, run_id: str) -> CrawlReport | None:
    if not run_id or any(character not in "0123456789TZ" for character in run_id):
        return None
    path = output_directory / "runs" / f"{run_id}.json"
    if not path.exists():
        return None
    return CrawlReport.model_validate(_read_json(path))


def list_history(output_directory: Path, limit: int = 3) -> list[CrawlReport]:
    latest = read_latest(output_directory)
    latest_id = latest.run_id if latest else None
    reports: list[CrawlReport] = []
    for path in (output_directory / "runs").glob("*.json"):
        try:
            report = CrawlReport.model_validate(_read_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if report.run_id != latest_id:
            reports.append(report)
    reports.sort(key=lambda report: report.finished_at, reverse=True)
    return reports[:limit]


def _prune_snapshots(runs_directory: Path, keep: int) -> None:
    valid: list[tuple[CrawlReport, Path]] = []
    for path in runs_directory.glob("*.json"):
        try:
            valid.append((CrawlReport.model_validate(_read_json(path)), path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    valid.sort(key=lambda item: item[0].finished_at, reverse=True)
    for _, path in valid[keep:]:
        path.unlink(missing_ok=True)
