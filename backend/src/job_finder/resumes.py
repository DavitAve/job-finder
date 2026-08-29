from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from filelock import FileLock, Timeout as FileLockTimeout
from pydantic import BaseModel, Field
from pypdf import PdfReader

from job_finder.models import Job

if TYPE_CHECKING:
    from job_finder.database import DatabaseStore


MAX_RESUMES = 3
MAX_PDF_BYTES = 5 * 1024 * 1024


class ResumeError(ValueError):
    pass


class ResumeBusyError(RuntimeError):
    pass


class ResumeRecord(BaseModel):
    id: str
    filename: str
    language: Literal["en", "ru"]
    created_at: datetime
    size_bytes: int
    page_count: int
    skills: list[str] = Field(default_factory=list)
    text: str = ""


class ResumeSummary(BaseModel):
    id: str
    filename: str
    language: Literal["en", "ru"]
    created_at: datetime
    size_bytes: int
    page_count: int
    skills: list[str] = Field(default_factory=list)
    active: bool = False


class ResumeList(BaseModel):
    resumes: list[ResumeSummary]
    active_id: str | None = None
    limit: int = MAX_RESUMES


class ResumeMatch(BaseModel):
    job_id: str
    score: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    vacancy_skills: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ResumeMatches(BaseModel):
    active_resume_id: str | None = None
    matches: list[ResumeMatch] = Field(default_factory=list)


_SKILLS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        ("React", r"\breact(?:\.js|js)?\b"),
        ("Vue", r"\bvue(?:\.js|js)?\b"),
        ("Angular", r"\bangular\b"),
        ("JavaScript", r"\b(?:javascript|java script|js)\b"),
        ("TypeScript", r"\b(?:typescript|type script|ts)\b"),
        ("Next.js", r"\bnext(?:\.js|js)?\b"),
        ("Nuxt", r"\bnuxt(?:\.js|js)?\b"),
        ("HTML", r"\bhtml5?\b"),
        ("CSS", r"\b(?:css3?|scss|sass)\b"),
        ("Redux", r"\bredux(?: toolkit)?\b"),
        ("Node.js", r"\bnode(?:\.js|js)?\b"),
        ("GraphQL", r"\bgraphql\b"),
        ("REST", r"\brest(?:ful)?(?: api)?\b"),
        ("Git", r"\bgit\b"),
        ("Jest", r"\bjest\b"),
        ("Vitest", r"\bvitest\b"),
        ("Cypress", r"\bcypress\b"),
        ("Playwright", r"\bplaywright\b"),
        ("Webpack", r"\bwebpack\b"),
        ("Vite", r"\bvite\b"),
        ("Tailwind CSS", r"\btailwind(?: css)?\b"),
        ("Docker", r"\bdocker\b"),
        ("AWS", r"\baws\b|amazon web services"),
        ("Figma", r"\bfigma\b"),
    )
)
_TITLE_WORDS = re.compile(
    r"\b(frontend|front-end|developer|engineer|react|vue|angular|javascript|typescript|"
    r"senior|middle|junior|lead|ui|web|разработчик|фронтенд)\b",
    re.IGNORECASE,
)
_FRONTEND_ROLE = re.compile(r"\b(front[\s-]?end|ui|web|фронтенд|веб)\b", re.IGNORECASE)
_DEVELOPER_ROLE = re.compile(r"\b(developer|engineer|разработчик|инженер)\b", re.IGNORECASE)
_SENIORITY_EQUIVALENTS = {
    "senior": re.compile(r"\b(senior|sr\.?|старший)\b", re.IGNORECASE),
    "middle": re.compile(r"\b(middle|mid|средний)\b", re.IGNORECASE),
    "junior": re.compile(r"\b(junior|jr\.?|младший)\b", re.IGNORECASE),
    "lead": re.compile(r"\b(lead|ведущий)\b", re.IGNORECASE),
}


def extract_skills(text: str) -> list[str]:
    return [name for name, pattern in _SKILLS if pattern.search(text)]


def _extract_pdf(content: bytes) -> tuple[str, int]:
    if not content.startswith(b"%PDF-"):
        raise ResumeError("The uploaded file is not a PDF")
    if len(content) > MAX_PDF_BYTES:
        raise ResumeError("PDF is larger than 5 MB")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ResumeError("Password-protected PDFs are not supported")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except ResumeError:
        raise
    except Exception as exc:
        raise ResumeError(f"Cannot read PDF: {exc}") from exc
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()
    if len(text) < 30:
        raise ResumeError("No readable text was found in the PDF; scanned PDFs need OCR")
    return text[:100_000], len(reader.pages)


class ResumeStore:
    def __init__(self, directory: Path, database: DatabaseStore | None = None) -> None:
        self.directory = directory
        self.index_path = directory / "index.json"
        self.lock = FileLock(str(directory / "resumes.lock"))
        self.database = database
        if database is not None:
            records, _ = database.read_resumes()
            if not records and self.index_path.exists():
                legacy_records, active_id = self._read_index()
                database.replace_resumes(
                    [record.model_dump(mode="json") for record in legacy_records],
                    active_id,
                    directory,
                )

    def _read_index(self) -> tuple[list[ResumeRecord], str | None]:
        if not self.index_path.exists():
            return [], None
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        return [ResumeRecord.model_validate(item) for item in data.get("resumes", [])], data.get("active_id")

    def _read(self) -> tuple[list[ResumeRecord], str | None]:
        if self.database is None:
            return self._read_index()
        records, active_id = self.database.read_resumes()
        return [ResumeRecord.model_validate(item) for item in records], active_id

    def _write(self, records: list[ResumeRecord], active_id: str | None) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_id": active_id,
            "resumes": [record.model_dump(mode="json") for record in records],
        }
        if self.database is not None:
            self.database.replace_resumes(payload["resumes"], active_id, self.directory)
        handle, temporary = tempfile.mkstemp(prefix="resumes-", suffix=".json.tmp", dir=self.directory)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.index_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _summary(self, records: list[ResumeRecord], active_id: str | None) -> ResumeList:
        return ResumeList(
            resumes=[
                ResumeSummary(**record.model_dump(exclude={"text"}), active=record.id == active_id)
                for record in records
            ],
            active_id=active_id,
        )

    def list(self) -> ResumeList:
        records, active_id = self._read()
        return self._summary(records, active_id)

    def active(self) -> ResumeRecord | None:
        records, active_id = self._read()
        return next((record for record in records if record.id == active_id), None)

    def add(self, content: bytes, filename: str, language: Literal["en", "ru"]) -> ResumeList:
        if Path(filename).suffix.casefold() != ".pdf":
            raise ResumeError("Only PDF resumes are supported")
        text, page_count = _extract_pdf(content)
        resume_id = hashlib.sha256(content).hexdigest()[:16]
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock.acquire(timeout=0):
                records, active_id = self._read()
                if any(record.id == resume_id for record in records):
                    raise ResumeError("This resume has already been uploaded")
                if len(records) >= MAX_RESUMES:
                    raise ResumeError("You can store no more than 3 resumes")
                record = ResumeRecord(
                    id=resume_id,
                    filename=Path(filename).name[:255],
                    language=language,
                    created_at=datetime.now(timezone.utc),
                    size_bytes=len(content),
                    page_count=page_count,
                    skills=extract_skills(text),
                    text=text,
                )
                pdf_path = self.directory / f"{resume_id}.pdf"
                pdf_path.write_bytes(content)
                try:
                    records.append(record)
                    self._write(records, active_id or resume_id)
                except BaseException:
                    pdf_path.unlink(missing_ok=True)
                    raise
                return self._summary(records, active_id or resume_id)
        except FileLockTimeout as exc:
            raise ResumeBusyError("Resume storage is busy") from exc

    def activate(self, resume_id: str) -> ResumeList:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock.acquire(timeout=0):
                records, _ = self._read()
                if not any(record.id == resume_id for record in records):
                    raise ResumeError("Resume not found")
                self._write(records, resume_id)
                return self._summary(records, resume_id)
        except FileLockTimeout as exc:
            raise ResumeBusyError("Resume storage is busy") from exc

    def delete(self, resume_id: str) -> ResumeList:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock.acquire(timeout=0):
                records, active_id = self._read()
                remaining = [record for record in records if record.id != resume_id]
                if len(remaining) == len(records):
                    raise ResumeError("Resume not found")
                new_active = remaining[0].id if active_id == resume_id and remaining else active_id
                pdf_path = self.directory / f"{resume_id}.pdf"
                trash = self.directory / ".trash"
                if pdf_path.exists():
                    trash.mkdir(exist_ok=True)
                    shutil.move(str(pdf_path), trash / f"{resume_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.pdf")
                self._write(remaining, new_active)
                return self._summary(remaining, new_active)
        except FileLockTimeout as exc:
            raise ResumeBusyError("Resume storage is busy") from exc


def score_job(job: Job, resume: ResumeRecord) -> ResumeMatch:
    vacancy_text = f"{job.title}\n{job.description}"
    vacancy_skills = set(extract_skills(vacancy_text)) | set(job.technologies)
    resume_skills = set(resume.skills)
    matched = sorted(vacancy_skills & resume_skills)
    reasons: list[str] = []
    score = 0.0
    if vacancy_skills:
        coverage = len(matched) / len(vacancy_skills)
        score += coverage * 70
        if matched:
            reasons.append(f"Совпавшие навыки: {', '.join(matched)}")
    title_terms = {match.group(0).casefold() for match in _TITLE_WORDS.finditer(job.title)}
    resume_terms = {match.group(0).casefold() for match in _TITLE_WORDS.finditer(resume.text)}
    common_terms = title_terms & resume_terms
    if common_terms:
        score += min(20, 5 * len(common_terms))
        reasons.append("Роль соответствует профилю резюме")
    elif (
        _FRONTEND_ROLE.search(job.title)
        and _FRONTEND_ROLE.search(resume.text)
        and _DEVELOPER_ROLE.search(job.title)
        and _DEVELOPER_ROLE.search(resume.text)
    ):
        score += 15
        reasons.append("Frontend-роль соответствует профилю резюме")
    seniority_pattern = _SENIORITY_EQUIVALENTS.get(job.seniority or "")
    if seniority_pattern and seniority_pattern.search(resume.text):
        score += 10
        reasons.append(f"Совпадает уровень: {job.seniority}")
    elif not job.seniority:
        score += 5
    return ResumeMatch(
        job_id=job.job_id,
        score=min(100, round(score)),
        matched_skills=matched,
        vacancy_skills=sorted(vacancy_skills),
        reasons=reasons,
    )
