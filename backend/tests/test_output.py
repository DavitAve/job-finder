from datetime import datetime, timedelta, timezone

import json

from job_finder.models import (
    CompanyCrawlResult,
    CompanyStatus,
    CrawlReport,
    CrawlStats,
    Job,
    WorkFormat,
)
from job_finder.output import list_history, read_company_history, read_latest, read_run, write_report
import job_finder.output as output_module


def report(index: int) -> CrawlReport:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    return CrawlReport(
        run_id=started.strftime("%Y%m%dT%H%M%S%fZ"),
        started_at=started,
        finished_at=started + timedelta(seconds=10),
        stats=CrawlStats(total_companies=0),
        companies=[],
        errors=[],
        jobs=[],
    )


def test_storage_keeps_current_and_three_previous_runs(tmp_path) -> None:
    reports = [report(index) for index in range(5)]
    for item in reports:
        write_report(item, tmp_path)

    assert read_latest(tmp_path).run_id == reports[-1].run_id  # type: ignore[union-attr]
    assert [item.run_id for item in list_history(tmp_path)] == [
        reports[3].run_id,
        reports[2].run_id,
        reports[1].run_id,
    ]
    assert len(list((tmp_path / "runs").glob("*.json"))) == 4
    assert read_run(tmp_path, reports[0].run_id) is None


def test_compact_company_history_keeps_five_actual_checks(tmp_path) -> None:
    reports = [report(index) for index in range(6)]
    for index, item in enumerate(reports):
        item.processed_company_ids = ["acme"]
        item.companies = [CompanyCrawlResult(
            company_id="acme",
            company="Acme",
            careers_url="https://acme.example/jobs",
            resolved_careers_url=f"https://jobs.example/acme/{index}",
            status=CompanyStatus.SUCCESS if index % 2 else CompanyStatus.FAILED,
            adapter="greenhouse" if index % 2 else "html",
            matching_jobs=index,
            error=None if index % 2 else "Temporary error",
            duration_ms=100 + index,
            last_crawled_at=item.finished_at,
        )]
        write_report(item, tmp_path)

    history = read_company_history(tmp_path, "acme")

    assert len(history) == 5
    assert [entry["run_id"] for entry in history] == [item.run_id for item in reversed(reports[1:])]
    assert history[0]["jobs_found"] == 5
    assert history[-1]["jobs_found"] == 1


def test_invalid_run_id_cannot_escape_runs_directory(tmp_path) -> None:
    assert read_run(tmp_path, "../latest") is None


def test_schema_v1_remote_job_is_upgraded_when_read(tmp_path) -> None:
    legacy = report(1).model_dump(mode="json")
    legacy["schema_version"] = "1.0"
    legacy["jobs"] = [
        Job(
            job_id="job-1",
            company="Acme",
            title="Frontend Developer",
            url="https://example.com/jobs/1",
            remote=True,
            source="html",
            found_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ).model_dump(mode="json", exclude={"work_format", "source_job_id"})
    ]
    (tmp_path / "latest.json").write_text(__import__("json").dumps(legacy), encoding="utf-8")
    loaded = read_latest(tmp_path)
    assert loaded is not None
    assert loaded.jobs[0].work_format == WorkFormat.REMOTE


def test_legacy_company_result_uses_report_finish_as_last_crawl_time(tmp_path) -> None:
    legacy = report(1).model_dump(mode="json")
    legacy["companies"] = [
        CompanyCrawlResult(
            company_id="acme",
            company="Acme",
            status=CompanyStatus.NO_JOBS,
        ).model_dump(mode="json")
    ]
    legacy["companies"][0].pop("last_crawled_at")
    (tmp_path / "latest.json").write_text(json.dumps(legacy), encoding="utf-8")

    loaded = read_latest(tmp_path)

    assert loaded is not None
    assert loaded.companies[0].last_crawled_at == loaded.finished_at


def test_failed_latest_commit_rolls_back_new_snapshot(tmp_path, monkeypatch) -> None:
    original = output_module._write_json_atomic
    old = report(1)
    new = report(2)
    write_report(old, tmp_path)
    history_before = sorted(path.name for path in (tmp_path / "runs").glob("*.json"))

    def fail_latest(path, payload) -> None:
        if path.name == "latest.json":
            raise OSError("disk unavailable")
        original(path, payload)

    monkeypatch.setattr(output_module, "_write_json_atomic", fail_latest)
    try:
        write_report(new, tmp_path)
    except OSError:
        pass
    else:
        raise AssertionError("write_report should propagate a failed latest commit")

    assert read_latest(tmp_path).run_id == old.run_id  # type: ignore[union-attr]
    assert sorted(path.name for path in (tmp_path / "runs").glob("*.json")) == history_before
    assert not (tmp_path / "latest.json.tmp").exists()


def test_prune_failure_does_not_fail_committed_report(tmp_path, monkeypatch) -> None:
    new = report(2)

    def fail_prune(*args, **kwargs) -> None:
        raise OSError("file temporarily busy")

    monkeypatch.setattr(output_module, "_prune_snapshots", fail_prune)
    latest, snapshot = write_report(new, tmp_path)

    assert latest.exists() and snapshot.exists()
    assert read_latest(tmp_path).run_id == new.run_id  # type: ignore[union-attr]


def test_discovered_careers_urls_are_written_as_suggestions(tmp_path) -> None:
    item = report(3)
    item.companies = [
        CompanyCrawlResult(
            company_id="acme",
            company="Acme",
            careers_url="https://acme.example/old",
            resolved_careers_url="https://jobs.lever.co/acme",
            careers_url_discovered=True,
            status=CompanyStatus.SUCCESS,
        )
    ]

    write_report(item, tmp_path)

    payload = json.loads((tmp_path / "discovered-careers.json").read_text("utf-8"))
    assert payload["run_id"] == item.run_id
    assert payload["discoveries"] == [
        {
            "company_id": "acme",
            "company": "Acme",
            "configured_careers_url": "https://acme.example/old",
            "resolved_careers_url": "https://jobs.lever.co/acme",
        }
    ]
