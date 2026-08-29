"""Keep five company checks independently of run retention.

Revision ID: 20260828_0002
Revises: 20260828_0001
"""
from alembic import op
from sqlalchemy import inspect

from job_finder.database import CompanyHistoryRow


revision = "20260828_0002"
down_revision = "20260828_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(CompanyHistoryRow.__tablename__):
        CompanyHistoryRow.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(CompanyHistoryRow.__tablename__):
        CompanyHistoryRow.__table__.drop(bind=bind)
