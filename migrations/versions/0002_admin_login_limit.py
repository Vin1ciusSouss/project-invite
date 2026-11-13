"""Contagem compartilhada das tentativas de acesso administrativo."""
from alembic import op
import sqlalchemy as sa

revision = "0002_admin_login_limit"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("admin_login_limit",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started", sa.BigInteger(), nullable=False),
    )


def downgrade():
    op.drop_table("admin_login_limit")
