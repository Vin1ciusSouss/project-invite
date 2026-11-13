"""Esquema inicial e adoção dos bancos SQLite das versões anteriores."""
from secrets import token_urlsafe

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "invite_group" not in tables:
        op.create_table("invite_group",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reference_name", sa.String(120), nullable=False, unique=True),
            sa.Column("guest_names", sa.Text(), nullable=False),
            sa.Column("invite_token", sa.String(64)),
        )
    if "gift" not in tables:
        op.create_table("gift",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("description", sa.String(300), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("emoji", sa.String(12), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("reserved_by", sa.String(120)),
            sa.Column("reserved_at", sa.DateTime()),
            sa.Column("gift_type", sa.String(20), nullable=False),
            sa.Column("external_url", sa.String(1000)),
            sa.Column("image_filename", sa.String(255)),
        )
    if "rsvp" not in tables:
        op.create_table("rsvp",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("guest_name", sa.String(120), nullable=False),
            sa.Column("email", sa.String(254), nullable=False),
            sa.Column("attendance", sa.String(10), nullable=False),
            sa.Column("invite_group_id", sa.Integer(), sa.ForeignKey("invite_group.id", ondelete="SET NULL")),
            sa.Column("guest_count", sa.Integer(), nullable=False),
            sa.Column("companion_names", sa.Text(), nullable=False),
            sa.Column("attendee_names", sa.Text(), nullable=False),
            sa.Column("invite_guest_names", sa.Text(), nullable=False),
            sa.Column("message", sa.String(500)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    additions = {
        "invite_group": [sa.Column("invite_token", sa.String(64))],
        "gift": [
            sa.Column("gift_type", sa.String(20), nullable=False, server_default="reservation"),
            sa.Column("external_url", sa.String(1000)),
            sa.Column("image_filename", sa.String(255)),
        ],
        "rsvp": [
            sa.Column("companion_names", sa.Text(), nullable=False, server_default=""),
            sa.Column("attendee_names", sa.Text(), nullable=False, server_default=""),
            sa.Column("invite_guest_names", sa.Text(), nullable=False, server_default=""),
            sa.Column("invite_group_id", sa.Integer(), sa.ForeignKey("invite_group.id", ondelete="SET NULL")),
        ],
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                # SQLite cannot add a separate FK constraint without rebuilding.
                if table == "rsvp" and column.name == "invite_group_id" and bind.dialect.name == "sqlite":
                    op.execute("ALTER TABLE rsvp ADD COLUMN invite_group_id INTEGER REFERENCES invite_group(id) ON DELETE SET NULL")
                else:
                    op.add_column(table, column)

    missing_ids = bind.execute(sa.text("SELECT id FROM invite_group WHERE invite_token IS NULL OR invite_token = ''")).scalars().all()
    for group_id in missing_ids:
        bind.execute(sa.text("UPDATE invite_group SET invite_token = :token WHERE id = :id"), {"token": token_urlsafe(24), "id": group_id})

    # Preserve older responses as history; only the latest stays linked to a group.
    responses = bind.execute(sa.text("SELECT id, invite_group_id FROM rsvp WHERE invite_group_id IS NOT NULL ORDER BY created_at DESC, id DESC")).all()
    seen_groups = set()
    for response_id, group_id in responses:
        if group_id in seen_groups:
            bind.execute(sa.text("UPDATE rsvp SET invite_group_id = NULL WHERE id = :id"), {"id": response_id})
        seen_groups.add(group_id)

    rsvp_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("rsvp")}
    if "uq_rsvp_email" in rsvp_indexes:
        op.drop_index("uq_rsvp_email", table_name="rsvp")
    for table, name, column in [
        ("invite_group", "uq_invite_group_token", "invite_token"),
        ("rsvp", "uq_rsvp_invite_group", "invite_group_id"),
    ]:
        if name not in {index["name"] for index in sa.inspect(bind).get_indexes(table)}:
            op.create_index(name, table, [column], unique=True)


def downgrade():
    raise RuntimeError("A versão inicial preserva bancos existentes. Para voltar, restaure o backup; não apague tabelas de convidados.")
