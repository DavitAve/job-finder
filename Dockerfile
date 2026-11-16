FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    JOB_FINDER_OUTPUT_DIR=/var/data/output \
    JOB_FINDER_RESUMES_DIR=/var/data/resumes \
    JOB_FINDER_COMPANIES_FILE=/var/data/companies.json \
    DATABASE_URL=sqlite:////var/data/job_finder.db \
    JOB_FINDER_AUTH_ENABLED=1 \
    JOB_FINDER_SECURE_COOKIES=1

WORKDIR /app/backend
COPY backend/ ./
RUN pip install --no-cache-dir -e . \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/ /app/deploy/
EXPOSE 8000
CMD ["python", "/app/deploy/start.py"]
