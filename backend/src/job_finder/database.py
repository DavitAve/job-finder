from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout as FileLockTimeout
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, delete, event, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from job_finder.excel import load_companies
from job_finder.models import Company, CompanyStatus, CrawlReport


LOCAL_USER_ID = "local"


class DatabaseBusyError(RuntimeError):
    pass


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="Local user")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SessionRow(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CompanyRow(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_company_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), index=True)
    website_url: Mapped[str] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    adapter: Mapped[str] = mapped_column(String(50), default="auto")
    adapter_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    company_metadata: Mapped[dict[str, str]] = mapped_column("metadata", JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CrawlRunRow(Base):
    __tablename__ = "crawl_runs"
    __table_args__ = (UniqueConstraint("user_id", "run_id", name="uq_run_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="2.0")
    scope: Mapped[str] = mapped_column(String(30), default="full")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    checks: Mapped[list[CompanyCheckRow]] = relationship(back_populates="run", cascade="all, delete-orphan")
    jobs: Mapped[list[JobSnapshotRow]] = relationship(back_populates="run", cascade="all, delete-orphan")


class CompanyCheckRow(Base):
    __tablename__ = "company_checks"
    __table_args__ = (UniqueConstraint("run_db_id", "company_id", name="uq_check_run_company"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_db_id: Mapped[int] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    run: Mapped[CrawlRunRow] = relationship(back_populates="checks")


class CompanyHistoryRow(Base):
    __tablename__ = "company_history"
    __table_args__ = (UniqueConstraint("user_id", "company_id", "run_id", name="uq_history_user_company_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class JobSnapshotRow(Base):
    __tablename__ = "job_snapshots"
    __table_args__ = (UniqueConstraint("run_db_id", "job_id", name="uq_job_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_db_id: Mapped[int] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(String(128), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    run: Mapped[CrawlRunRow] = relationship(back_populates="jobs")


class ResumeRow(Base):
    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("user_id", "resume_id", name="uq_resume_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class DatabaseStore:
    """User-scoped persistence with a SQLite default and PostgreSQL-compatible schema."""

    def __init__(self, database_url: str, *, user_id: str = LOCAL_USER_ID) -> None:
        self.database_url = database_url
        self.user_id = user_id
        if database_url.startswith("sqlite"):
            database_name = make_url(database_url).database
            if database_name and database_name != ":memory:":
                Path(database_name).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
        if database_url.startswith("sqlite"):
            event.listen(self.engine, "connect", _configure_sqlite)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            if session.get(UserRow, self.user_id) is None:
                session.add(UserRow(
                    id=self.user_id,
                    email=f"{self.user_id}@job-finder.invalid",
                    display_name="Local user" if self.user_id == LOCAL_USER_ID else self.user_id,
                ))

    def scoped(self, user_id: str) -> DatabaseStore:
        scoped = object.__new__(DatabaseStore)
        scoped.database_url = self.database_url
        scoped.user_id = user_id
        scoped.engine = self.engine
        scoped.sessions = self.sessions
        return scoped

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.scalar(select(UserRow).where(UserRow.email == email).limit(1))
            return self._user(row)

    def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            return self._user(session.get(UserRow, user_id))

    def register_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        claim_local: bool = True,
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            if session.scalar(select(UserRow.id).where(UserRow.email == email).limit(1)):
                raise ValueError("An account with this email already exists")
            local = session.get(UserRow, LOCAL_USER_ID) if claim_local else None
            if local is not None and local.password_hash is None:
                local.email = email
                local.display_name = display_name
                local.password_hash = password_hash
                session.flush()
                return self._user(local)  # type: ignore[return-value]
            row = UserRow(
                id=str(uuid.uuid4()),
                email=email,
                display_name=display_name,
                password_hash=password_hash,
            )
            session.add(row)
            session.flush()
            return self._user(row)  # type: ignore[return-value]

    def create_auth_session(self, *, token_hash: str, user_id: str, expires_at: datetime) -> None:
        with self.sessions.begin() as session:
            session.add(SessionRow(
                token_hash=token_hash,
                user_id=user_id,
                expires_at=expires_at,
            ))

    def resolve_auth_session(self, token_hash: str, now: datetime) -> dict[str, Any] | None:
        with self.sessions.begin() as session:
            row = session.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash).limit(1))
            if row is None:
                return None
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                session.delete(row)
                return None
            user = session.get(UserRow, row.user_id)
            if user is None or user.password_hash is None:
                session.delete(row)
                return None
            row.last_seen_at = now
            return self._user(user)

    def delete_auth_session(self, token_hash: str) -> None:
        with self.sessions.begin() as session:
            session.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash))

    @staticmethod
    def _user(row: UserRow | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "email": row.email,
            "display_name": row.display_name,
            "password_hash": row.password_hash,
            "created_at": row.created_at,
        }

    def bootstrap_legacy(self, companies_path: Path, output_directory: Path) -> None:
        """One-time import. Existing database rows always win over legacy JSON."""
        self.initialize()
        if not self.list_companies() and companies_path.exists():
            self.replace_companies(load_companies(companies_path))
        self._bootstrap_company_history(output_directory / "company-history.json")
        with self.sessions() as session:
            has_runs = session.scalar(select(CrawlRunRow.id).where(CrawlRunRow.user_id == self.user_id).limit(1)) is not None
        if has_runs:
            return
        latest_path = output_directory / "latest.json"
        latest_id: str | None = None
        if latest_path.exists():
            try:
                latest_id = CrawlReport.model_validate_json(latest_path.read_text(encoding="utf-8")).run_id
            except (OSError, ValueError):
                pass
        candidates = list((output_directory / "runs").glob("*.json"))
        if latest_path.exists():
            candidates.append(latest_path)
        imported: set[str] = set()
        reports: list[CrawlReport] = []
        for path in candidates:
            try:
                report = CrawlReport.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if report.run_id not in imported:
                imported.add(report.run_id)
                reports.append(report)
        reports.sort(key=lambda item: item.finished_at)
        for report in reports:
            self.write_report(report, make_latest=report.run_id == latest_id, prune=False)

    def _bootstrap_company_history(self, legacy_path: Path) -> None:
        with self.sessions() as session:
            exists = session.scalar(
                select(CompanyHistoryRow.id)
                .where(CompanyHistoryRow.user_id == self.user_id)
                .limit(1)
            ) is not None
        if exists:
            return
        entries: list[tuple[str, dict[str, Any]]] = []
        if legacy_path.exists():
            try:
                payload = json.loads(legacy_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    entries = [
                        (company_id, item)
                        for company_id, history in payload.items()
                        if isinstance(company_id, str) and isinstance(history, list)
                        for item in history[:5]
                        if isinstance(item, dict)
                    ]
            except (OSError, ValueError):
                entries = []
        with self.sessions.begin() as session:
            if entries:
                for company_id, item in entries:
                    try:
                        session.add(CompanyHistoryRow(
                            user_id=self.user_id,
                            company_id=company_id,
                            run_id=str(item["run_id"]),
                            checked_at=_datetime(item["checked_at"]),
                            status=str(item["status"]),
                            careers_url=item.get("careers_url"),
                            adapter=item.get("adapter"),
                            jobs_found=int(item.get("jobs_found") or 0),
                            error=item.get("error"),
                            duration_ms=int(item.get("duration_ms") or 0),
                        ))
                    except (KeyError, TypeError, ValueError):
                        continue
                return
            retained = session.execute(
                select(CompanyCheckRow, CrawlRunRow.run_id)
                .join(CrawlRunRow, CrawlRunRow.id == CompanyCheckRow.run_db_id)
                .where(CompanyCheckRow.user_id == self.user_id)
            ).all()
            for row, run_id in retained:
                session.add(CompanyHistoryRow(
                    user_id=self.user_id,
                    company_id=row.company_id,
                    run_id=run_id,
                    checked_at=row.checked_at,
                    status=row.status,
                    careers_url=row.careers_url,
                    adapter=row.adapter,
                    jobs_found=row.jobs_found,
                    error=row.error,
                    duration_ms=row.duration_ms,
                ))

    def list_companies(self) -> list[Company]:
        with self.sessions() as session:
            rows = session.scalars(
                select(CompanyRow).where(CompanyRow.user_id == self.user_id).order_by(CompanyRow.sort_order, CompanyRow.id)
            ).all()
        return [self._company_from_row(row) for row in rows]

    def replace_companies(self, companies: list[Company]) -> None:
        if not companies:
            raise ValueError("The companies list cannot be empty")
        with self.sessions.begin() as session:
            session.execute(delete(CompanyRow).where(CompanyRow.user_id == self.user_id))
            for index, company in enumerate(companies):
                session.add(self._company_to_row(company, index))

    def mutate_companies(
        self,
        mutation: Callable[[list[Company]], list[Company]],
        *,
        lock_path: Path,
        backup_directory: Path,
    ) -> tuple[list[Company], Path]:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(lock_path))
        try:
            lock.acquire(timeout=0)
        except FileLockTimeout as exc:
            raise DatabaseBusyError("Cannot change companies while a crawl is running") from exc
        try:
            existing = self.list_companies()
            updated = mutation(existing)
            if not updated:
                raise ValueError("The companies list cannot be empty")
            backup_directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = backup_directory / f"companies-{stamp}.json"
            backup.write_text(json.dumps([item.model_dump(mode="json") for item in existing], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.replace_companies(updated)
            return updated, backup
        finally:
            lock.release()

    def write_report(self, report: CrawlReport, *, make_latest: bool = True, prune: bool = True) -> None:
        payload = report.model_dump(mode="json")
        processed_ids = set(report.processed_company_ids)
        if not processed_ids and report.scope == "full":
            processed_ids = {result.company_id for result in report.companies}
        with self.sessions.begin() as session:
            existing = session.scalar(select(CrawlRunRow).where(CrawlRunRow.user_id == self.user_id, CrawlRunRow.run_id == report.run_id))
            if existing is not None:
                session.delete(existing)
                session.flush()
            if make_latest:
                session.execute(update(CrawlRunRow).where(CrawlRunRow.user_id == self.user_id).values(is_latest=False))
            row = CrawlRunRow(
                user_id=self.user_id,
                run_id=report.run_id,
                schema_version=report.schema_version,
                scope=report.scope,
                started_at=report.started_at,
                finished_at=report.finished_at,
                is_latest=make_latest,
                stats=report.stats.model_dump(mode="json"),
                errors=[item.model_dump(mode="json") for item in report.errors],
                payload=payload,
            )
            session.add(row)
            session.flush()
            for result in report.companies:
                if result.company_id not in processed_ids or result.status == CompanyStatus.SKIPPED:
                    continue
                session.add(CompanyCheckRow(
                    run_db_id=row.id,
                    user_id=self.user_id,
                    company_id=result.company_id,
                    company=result.company,
                    checked_at=result.last_crawled_at or report.finished_at,
                    status=result.status.value,
                    careers_url=result.resolved_careers_url or result.careers_url,
                    adapter=result.adapter,
                    jobs_found=result.matching_jobs,
                    error=result.error,
                    duration_ms=result.duration_ms,
                    payload=result.model_dump(mode="json"),
                ))
                previous_history = session.scalar(select(CompanyHistoryRow).where(
                    CompanyHistoryRow.user_id == self.user_id,
                    CompanyHistoryRow.company_id == result.company_id,
                    CompanyHistoryRow.run_id == report.run_id,
                ))
                if previous_history is not None:
                    session.delete(previous_history)
                    session.flush()
                session.add(CompanyHistoryRow(
                    user_id=self.user_id,
                    company_id=result.company_id,
                    run_id=report.run_id,
                    checked_at=result.last_crawled_at or report.finished_at,
                    status=result.status.value,
                    careers_url=result.resolved_careers_url or result.careers_url,
                    adapter=result.adapter,
                    jobs_found=result.matching_jobs,
                    error=result.error,
                    duration_ms=result.duration_ms,
                ))
            for job in report.jobs:
                session.add(JobSnapshotRow(
                    run_db_id=row.id,
                    user_id=self.user_id,
                    job_id=job.job_id,
                    company=job.company,
                    title=job.title,
                    url=job.url,
                    source=job.source,
                    payload=job.model_dump(mode="json"),
                ))
            if prune:
                rows = session.scalars(
                    select(CrawlRunRow).where(CrawlRunRow.user_id == self.user_id).order_by(CrawlRunRow.finished_at.desc(), CrawlRunRow.id.desc())
                ).all()
                for stale in rows[4:]:
                    session.delete(stale)
                company_ids = set(report.processed_company_ids) or {
                    result.company_id for result in report.companies
                }
                for company_id in company_ids:
                    history_rows = session.scalars(
                        select(CompanyHistoryRow)
                        .where(
                            CompanyHistoryRow.user_id == self.user_id,
                            CompanyHistoryRow.company_id == company_id,
                        )
                        .order_by(CompanyHistoryRow.checked_at.desc(), CompanyHistoryRow.id.desc())
                    ).all()
                    for stale_history in history_rows[5:]:
                        session.delete(stale_history)

    def read_latest(self) -> CrawlReport | None:
        with self.sessions() as session:
            row = session.scalar(select(CrawlRunRow).where(CrawlRunRow.user_id == self.user_id, CrawlRunRow.is_latest.is_(True)).order_by(CrawlRunRow.finished_at.desc()).limit(1))
            return self._report(row)

    def read_run(self, run_id: str) -> CrawlReport | None:
        if not run_id or any(character not in "0123456789TZ" for character in run_id):
            return None
        with self.sessions() as session:
            row = session.scalar(select(CrawlRunRow).where(CrawlRunRow.user_id == self.user_id, CrawlRunRow.run_id == run_id).limit(1))
            return self._report(row)

    def list_history(self, limit: int = 3) -> list[CrawlReport]:
        with self.sessions() as session:
            rows = session.scalars(
                select(CrawlRunRow).where(CrawlRunRow.user_id == self.user_id, CrawlRunRow.is_latest.is_(False)).order_by(CrawlRunRow.finished_at.desc(), CrawlRunRow.id.desc()).limit(limit)
            ).all()
            return [report for row in rows if (report := self._report(row)) is not None]

    def read_company_history(self, company_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = session.scalars(
                select(CompanyHistoryRow)
                .where(CompanyHistoryRow.user_id == self.user_id, CompanyHistoryRow.company_id == company_id)
                .order_by(CompanyHistoryRow.checked_at.desc(), CompanyHistoryRow.id.desc())
                .limit(limit)
            ).all()
        return [{
            "run_id": row.run_id,
            "checked_at": _iso(row.checked_at),
            "status": row.status,
            "careers_url": row.careers_url,
            "adapter": row.adapter,
            "jobs_found": row.jobs_found,
            "error": row.error,
            "duration_ms": row.duration_ms,
        } for row in rows]

    def read_resumes(self) -> tuple[list[dict[str, Any]], str | None]:
        with self.sessions() as session:
            rows = session.scalars(
                select(ResumeRow)
                .where(ResumeRow.user_id == self.user_id)
                .order_by(ResumeRow.created_at, ResumeRow.id)
            ).all()
        records = [{
            "id": row.resume_id,
            "filename": row.filename,
            "language": row.language,
            "created_at": _iso(row.created_at),
            "size_bytes": row.size_bytes,
            "page_count": row.page_count,
            "skills": row.skills or [],
            "text": row.extracted_text,
        } for row in rows]
        active_id = next((row.resume_id for row in rows if row.is_active), None)
        return records, active_id

    def replace_resumes(
        self,
        records: list[dict[str, Any]],
        active_id: str | None,
        directory: Path,
    ) -> None:
        with self.sessions.begin() as session:
            session.execute(delete(ResumeRow).where(ResumeRow.user_id == self.user_id))
            for record in records:
                resume_id = str(record["id"])
                session.add(ResumeRow(
                    user_id=self.user_id,
                    resume_id=resume_id,
                    filename=str(record["filename"]),
                    language=str(record["language"]),
                    created_at=_datetime(record["created_at"]),
                    size_bytes=int(record["size_bytes"]),
                    page_count=int(record["page_count"]),
                    skills=list(record.get("skills") or []),
                    extracted_text=str(record.get("text") or ""),
                    file_path=str((directory / f"{resume_id}.pdf").resolve()),
                    is_active=resume_id == active_id,
                ))

    def _company_to_row(self, company: Company, order: int) -> CompanyRow:
        return CompanyRow(
            user_id=self.user_id,
            company_id=company.id,
            name=company.name,
            website_url=str(company.website_url),
            careers_url=str(company.careers_url) if company.careers_url else None,
            enabled=company.enabled,
            adapter=company.adapter,
            adapter_options=company.adapter_options,
            company_metadata=company.metadata,
            sort_order=order,
        )

    @staticmethod
    def _company_from_row(row: CompanyRow) -> Company:
        return Company(
            id=row.company_id,
            name=row.name,
            website_url=row.website_url,
            careers_url=row.careers_url,
            enabled=row.enabled,
            adapter=row.adapter,
            adapter_options=row.adapter_options or {},
            metadata=row.company_metadata or {},
        )

    @staticmethod
    def _report(row: CrawlRunRow | None) -> CrawlReport | None:
        return CrawlReport.model_validate(row.payload) if row is not None else None


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
