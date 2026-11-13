"""Alinha nulabilidade do e-mail histórico e a relação entre RSVP e convite."""
from alembic import op
import sqlalchemy as sa

revision = "0003_normalize_legacy_rsvp"
down_revision = "0002_admin_login_limit"
branch_labels = None
depends_on = None

FK_NAME = "fk_rsvp_invite_group_id_invite_group"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns("rsvp")}
    foreign_keys = [fk for fk in inspector.get_foreign_keys("rsvp") if fk["constrained_columns"] == ["invite_group_id"]]
    correct_fk = len(foreign_keys) == 1 and foreign_keys[0].get("options", {}).get("ondelete", "").upper() == "SET NULL"
    if columns["email"]["nullable"] and correct_fk:
        return
    with op.batch_alter_table("rsvp", naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}) as batch:
        if not columns["email"]["nullable"]:
            batch.alter_column("email", existing_type=sa.String(254), nullable=True)
        if not correct_fk:
            for fk in foreign_keys:
                batch.drop_constraint(fk["name"] or FK_NAME, type_="foreignkey")
            batch.create_foreign_key(FK_NAME, "invite_group", ["invite_group_id"], ["id"], ondelete="SET NULL")


def downgrade():
    raise RuntimeError("A normalização preserva e-mails históricos vazios. Para reverter o esquema legado, restaure o backup.")
