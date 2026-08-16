from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_finder.models import Company, Job, RawJob, WorkFormat


_EXPLICIT_FRONTEND = re.compile(
    r"\b(front[\s-]?end|frontend|ui\s+(?:engineer|developer)|web\s+developer)\b",
    re.IGNORECASE,
)
_ROLE = re.compile(r"\b(developer|engineer|programmer|architect)\b", re.IGNORECASE)
_EXCLUDED_TITLE = re.compile(
    r"\b(back[\s-]?end|backend|ios|android|mobile|qa|quality assurance|tester|"
    r"designer|product manager|project manager|engineering manager|devops|data engineer)\b",
    re.IGNORECASE,
)
_HARDWARE_FRONTEND = re.compile(
    r"\b(asic|fpga|rtl|vlsi|silicon|chip|emulation|physical design|"
    r"front[\s-]?end (?:power|integration)|hardware verification|"
    r"design verification|dft)\b",
    re.IGNORECASE,
)
_REMOTE = re.compile(r"\b(remote|work from home|distributed|anywhere)\b", re.IGNORECASE)
_HYBRID = re.compile(r"\b(hybrid|flexible office|office and remote)\b", re.IGNORECASE)
_ONSITE = re.compile(r"\b(on[\s-]?site|in[\s-]?office|office[\s-]?based)\b", re.IGNORECASE)

_TECHNOLOGIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("React", re.compile(r"\breact(?:\.js|js)?\b", re.IGNORECASE)),
    ("Vue", re.compile(r"\bvue(?:\.js|js)?\b", re.IGNORECASE)),
    ("Angular", re.compile(r"\bangular\b", re.IGNORECASE)),
    ("JavaScript", re.compile(r"\b(?:javascript|java script|js)\b", re.IGNORECASE)),
    ("TypeScript", re.compile(r"\b(?:typescript|type script|ts)\b", re.IGNORECASE)),
    ("Next.js", re.compile(r"\bnext(?:\.js|js)?\b", re.IGNORECASE)),
    ("Nuxt", re.compile(r"\bnuxt(?:\.js|js)?\b", re.IGNORECASE)),
    ("HTML", re.compile(r"\bhtml5?\b", re.IGNORECASE)),
    ("CSS", re.compile(r"\b(?:css3?|scss|sass)\b", re.IGNORECASE)),
    ("Redux", re.compile(r"\bredux\b", re.IGNORECASE)),
)

_SENIORITY: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internship", re.compile(r"\b(intern|internship|trainee)\b", re.IGNORECASE)),
    ("junior", re.compile(r"\b(junior|jr\.?)\b", re.IGNORECASE)),
    ("lead", re.compile(r"\b(lead|principal|staff|architect|head)\b", re.IGNORECASE)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE)),
    ("middle", re.compile(r"\b(mid(?:dle)?|intermediate)\b", re.IGNORECASE)),
)

_TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "source",
    "ref",
    "referrer",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMETERS
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def extract_technologies(text: str) -> list[str]:
    return [name for name, pattern in _TECHNOLOGIES if pattern.search(text)]


def detect_seniority(text: str) -> str | None:
    for value, pattern in _SENIORITY:
        if pattern.search(text):
            return value
    return None


def detect_work_format(text: str, remote: bool | None) -> WorkFormat:
    if _HYBRID.search(text):
        return WorkFormat.HYBRID
    if remote is True or _REMOTE.search(text):
        return WorkFormat.REMOTE
    if _ONSITE.search(text):
        return WorkFormat.ONSITE
    return WorkFormat.UNKNOWN


def frontend_match(title: str, description: str = "") -> tuple[bool, list[str]]:
    title = " ".join(title.split())
    description = " ".join(description.split())
    combined = f"{title}\n{description}"
    reasons: list[str] = []

    hardware_title = _HARDWARE_FRONTEND.search(title)
    if hardware_title and not extract_technologies(combined):
        return False, [f"excluded hardware role: {hardware_title.group(0).lower()}"]

    explicit_title = _EXPLICIT_FRONTEND.search(title)
    excluded_title = _EXCLUDED_TITLE.search(title)
    if excluded_title and not explicit_title:
        return False, [f"excluded title: {excluded_title.group(0).lower()}"]

    if explicit_title:
        reasons.append(f"frontend role in title: {explicit_title.group(0).lower()}")

    title_technologies = extract_technologies(title)
    if title_technologies and _ROLE.search(title):
        reasons.append(f"frontend technology in title: {', '.join(title_technologies)}")

    if reasons:
        return True, reasons

    description_explicit = _EXPLICIT_FRONTEND.search(description)
    technologies = extract_technologies(combined)
    if description_explicit and technologies:
        return True, [
            "frontend responsibility in description",
            f"frontend technologies: {', '.join(technologies)}",
        ]

    frontend_core = {"React", "Vue", "Angular", "JavaScript", "TypeScript", "HTML", "CSS"}
    core_hits = [technology for technology in technologies if technology in frontend_core]
    if _ROLE.search(title) and len(core_hits) >= 3:
        return True, [f"multiple frontend technologies: {', '.join(core_hits)}"]

    return False, []


def normalize_job(raw: RawJob, company: Company, found_at: datetime) -> Job | None:
    title = " ".join(raw.title.split()).strip()
    description = " ".join(raw.description.split()).strip()
    is_match, reasons = frontend_match(title, description)
    if not is_match or not raw.url:
        return None

    url = canonicalize_url(raw.url)
    location = " ".join(raw.location.split()).strip() if raw.location else None
    remote = raw.remote
    if remote is None:
        if _REMOTE.search(f"{title} {location or ''} {description[:1000]}"):
            remote = True
    technologies = extract_technologies(f"{title}\n{description}")
    seniority = detect_seniority(f"{title}\n{description[:500]}")
    source_job_id = raw.source_job_id.strip() if raw.source_job_id else None
    stable_key = (
        f"{company.id}\n{raw.source}\n{source_job_id}"
        if source_job_id
        else f"{company.id}\n{url}"
    )
    job_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    work_format = raw.work_format or detect_work_format(
        f"{title} {location or ''} {description[:1000]}", remote
    )

    return Job(
        job_id=job_id,
        company=company.name,
        title=title,
        url=url,
        location=location,
        remote=remote,
        work_format=work_format,
        seniority=seniority,
        technologies=technologies,
        description=description[:4000],
        published_at=raw.published_at,
        source=raw.source,
        source_job_id=source_job_id,
        found_at=found_at,
        match_reasons=reasons,
    )
