"""Add persistent authentication sessions.

Revision ID: 20260828_0003
Revises: 20260828_0002
"""
from alembic import op
from sqlalchemy import inspect

from job_finder.database import SessionRow


revision = "20260828_0003"
down_revision = "20260828_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(SessionRow.__tablename__):
        SessionRow.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(SessionRow.__tablename__):
        SessionRow.__table__.drop(bind=bind)
