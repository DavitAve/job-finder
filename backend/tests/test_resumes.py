from datetime import datetime, timezone

import pytest

from job_finder.models import Job
from job_finder.database import DatabaseStore
from job_finder.resumes import ResumeError, ResumeRecord, ResumeStore, score_job


def test_resume_store_limits_duplicates_and_tracks_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("job_finder.resumes._extract_pdf", lambda content: (f"Frontend React TypeScript {content!r}", 1))
    store = ResumeStore(tmp_path / "resumes")

    first = store.add(b"%PDF-first", "english.pdf", "en")
    second = store.add(b"%PDF-second", "russian.pdf", "ru")
    assert first.active_id == first.resumes[0].id
    assert len(second.resumes) == 2

    activated = store.activate(second.resumes[1].id)
    assert activated.active_id == second.resumes[1].id
    assert activated.resumes[1].active is True
    with pytest.raises(ResumeError, match="already"):
        store.add(b"%PDF-first", "duplicate.pdf", "en")

    store.add(b"%PDF-third", "third.pdf", "en")
    with pytest.raises(ResumeError, match="no more than 3"):
        store.add(b"%PDF-fourth", "fourth.pdf", "en")

    remaining = store.delete(activated.active_id)
    assert len(remaining.resumes) == 2
    assert remaining.active_id == remaining.resumes[0].id


def test_resume_store_uses_user_scoped_database(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("job_finder.resumes._extract_pdf", lambda content: ("Frontend Vue TypeScript", 1))
    database = DatabaseStore(f"sqlite:///{(tmp_path / 'job_finder.db').as_posix()}")
    database.initialize()
    directory = tmp_path / "resumes"

    created = ResumeStore(directory, database=database).add(b"%PDF-database", "resume.pdf", "en")
    reopened = ResumeStore(directory, database=database).list()

    assert reopened.active_id == created.active_id
    assert reopened.resumes[0].skills == ["Vue", "TypeScript"]


def test_resume_match_scores_relevant_job_higher() -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    resume = ResumeRecord(
        id="resume",
        filename="resume.pdf",
        language="en",
        created_at=now,
        size_bytes=100,
        page_count=1,
        skills=["React", "TypeScript", "Redux"],
        text="Senior Frontend Developer React TypeScript Redux",
    )
    relevant = Job(
        job_id="relevant", company="Acme", title="Senior React Developer",
        url="https://example.com/relevant", source="test", found_at=now,
        seniority="senior", technologies=["React", "TypeScript"], description="Redux frontend",
    )
    weak = relevant.model_copy(update={
        "job_id": "weak", "title": "Angular Developer", "seniority": "junior",
        "technologies": ["Angular"], "description": "Angular",
    })

    relevant_score = score_job(relevant, resume)
    weak_score = score_job(weak, resume)

    assert relevant_score.score > weak_score.score
    assert relevant_score.score >= 80
    assert relevant_score.matched_skills == ["React", "Redux", "TypeScript"]
