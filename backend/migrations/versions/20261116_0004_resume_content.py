"""Keep PDF originals in the database for deployments without persistent disks."""
from alembic import op
import sqlalchemy as sa

revision = '20261116_0004'
down_revision = '20260828_0003'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('resumes')}
    if 'pdf_content' not in columns:
        op.add_column('resumes', sa.Column('pdf_content', sa.LargeBinary(), nullable=True))


def downgrade():
    op.drop_column('resumes', 'pdf_content')
