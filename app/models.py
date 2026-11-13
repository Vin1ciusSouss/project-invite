from datetime import datetime, timezone
from secrets import token_urlsafe
from .extensions import db


class AdminLoginLimit(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    attempts = db.Column(db.Integer, nullable=False)
    window_started = db.Column(db.BigInteger, nullable=False)

class InviteGroup(db.Model):
    __table_args__ = (db.Index("uq_invite_group_token", "invite_token", unique=True),)

    id = db.Column(db.Integer, primary_key=True)
    reference_name = db.Column(db.String(120), nullable=False, unique=True)
    guest_names = db.Column(db.Text, nullable=False)
    invite_token = db.Column(db.String(64), nullable=True, default=lambda: token_urlsafe(24))

class Gift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300), nullable=False, default="")
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    emoji = db.Column(db.String(12), nullable=False, default="🎁")
    status = db.Column(db.String(20), nullable=False, default="available")
    reserved_by = db.Column(db.String(120), nullable=True)
    reserved_at = db.Column(db.DateTime, nullable=True)
    gift_type = db.Column(db.String(20), nullable=False, default="reservation")
    external_url = db.Column(db.String(1000), nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)

class RSVP(db.Model):
    __table_args__ = (db.Index("uq_rsvp_invite_group", "invite_group_id", unique=True),)

    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(120), nullable=False)
    # Mantido para preservar respostas antigas; não é coletado no RSVP atual.
    email = db.Column(db.String(254), nullable=True)
    attendance = db.Column(db.String(10), nullable=False)
    invite_group_id = db.Column(db.Integer, db.ForeignKey("invite_group.id", ondelete="SET NULL"), nullable=True)
    guest_count = db.Column(db.Integer, nullable=False, default=1)
    companion_names = db.Column(db.Text, nullable=False, default="")
    attendee_names = db.Column(db.Text, nullable=False, default="")
    invite_guest_names = db.Column(db.Text, nullable=False, default="")
    message = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
