from functools import wraps
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe
import re
import unicodedata
from uuid import uuid4
from urllib.parse import urlsplit

import qrcode

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, send_file, session, url_for
from PIL import Image, UnidentifiedImageError
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, update
from werkzeug.security import check_password_hash

from .extensions import db
from .forms import AdminLoginForm, AdminRSVPForm, GiftForm, InviteGroupForm
from .models import Gift, InviteGroup, RSVP
from .login_limits import clear_attempts, reserve_attempt

admin = Blueprint("admin", __name__, url_prefix="/admin")


def _save_gift_image(upload):
    extension = Path(upload.filename or "").suffix.lower()
    expected_formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
    expected_format = expected_formats.get(extension)
    if not expected_format:
        raise ValueError("Envie uma imagem PNG, JPG, JPEG ou WebP.")

    try:
        upload.stream.seek(0)
        upload_size = upload.stream.seek(0, 2)
        upload.stream.seek(0)
        if upload_size > 5 * 1024 * 1024:
            raise ValueError("A imagem deve ter no máximo 5 MB.")
        with Image.open(upload.stream) as image:
            if image.format != expected_format:
                raise ValueError("A extensão do arquivo não corresponde ao formato da imagem.")
            if image.width * image.height > 20_000_000:
                raise ValueError("A imagem é muito grande. Reduza as dimensões antes de enviar.")
            image.load()
            normalized_image = image.copy()
            if expected_format == "JPEG" and normalized_image.mode not in ("RGB", "L"):
                normalized_image = normalized_image.convert("RGB")
            normalized_stream = BytesIO()
            normalized_image.save(normalized_stream, format=expected_format, optimize=True)
            normalized_stream.seek(0)
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("O arquivo não contém uma imagem válida ou está corrompido.") from error

    filename = f"{uuid4().hex}{extension}"
    upload_folder = Path(current_app.config["GIFT_UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    (upload_folder / filename).write_bytes(normalized_stream.getvalue())
    return filename


def _delete_gift_image(filename):
    if not filename or Path(filename).name != filename:
        return
    image_path = Path(current_app.config["GIFT_UPLOAD_FOLDER"]) / filename
    try:
        image_path.unlink(missing_ok=True)
    except OSError:
        current_app.logger.exception("Não foi possível remover o arquivo de imagem %s", filename)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@admin.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin.dashboard"))

    form = AdminLoginForm()
    password_hash = current_app.config.get("ADMIN_PASSWORD_HASH", "")
    if form.validate_on_submit():
        if not password_hash:
            flash("O acesso administrativo ainda não foi configurado. Defina ADMIN_PASSWORD_HASH no arquivo .env.", "error")
        else:
            retry_after = reserve_attempt(request.remote_addr)
            if retry_after:
                minutes = (retry_after + 59) // 60
                unit = "minuto" if minutes == 1 else "minutos"
                form.password.errors.append(f"Muitas tentativas de acesso. Aguarde {minutes} {unit} e tente novamente.")
                response = make_response(render_template("admin/login.html", form=form, configured=True), 429)
                response.headers["Retry-After"] = str(retry_after)
                return response
            try:
                password_matches = check_password_hash(password_hash, form.password.data)
            except (ValueError, TypeError):
                password_matches = False
                current_app.logger.error("ADMIN_PASSWORD_HASH inválido; gere novamente o hash e copie o valor completo para .env.")

            if password_matches:
                clear_attempts(request.remote_addr)
                session.clear()
                session["admin_authenticated"] = True
                flash("Acesso autorizado.", "success")
                return redirect(url_for("admin.dashboard"))
            flash("A senha ou a configuração do acesso está incorreta. Confira o hash completo no .env.", "error")
    return render_template("admin/login.html", form=form, configured=bool(password_hash))


@admin.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Você saiu do painel administrativo.", "success")
    return redirect(url_for("admin.login"))


@admin.get("/")
@login_required
def dashboard():
    rsvps = RSVP.query.order_by(RSVP.created_at.desc(), RSVP.id.desc()).all()
    invite_groups = InviteGroup.query.order_by(InviteGroup.reference_name.asc()).all()
    invite_responses = {rsvp.invite_group_id: rsvp for rsvp in rsvps if rsvp.invite_group_id is not None}
    gifts = Gift.query.order_by(Gift.id.asc()).all()
    confirmed_count = RSVP.query.filter_by(attendance="yes").count()
    guest_total = db.session.query(func.coalesce(func.sum(RSVP.guest_count), 0)).filter_by(attendance="yes").scalar()
    return render_template(
        "admin/dashboard.html",
        rsvps=rsvps,
        invite_groups=invite_groups,
        invite_responses=invite_responses,
        gifts=gifts,
        confirmed_count=confirmed_count,
        guest_total=guest_total,
    )


@admin.route("/confirmacoes/<int:rsvp_id>/editar", methods=["GET", "POST"])
@login_required
def edit_rsvp(rsvp_id):
    rsvp = db.get_or_404(RSVP, rsvp_id)
    form = AdminRSVPForm(obj=rsvp)
    roster = [name.strip() for name in (rsvp.invite_guest_names or "").splitlines() if name.strip()]
    if not roster and rsvp.invite_group_id:
        invite_group = db.session.get(InviteGroup, rsvp.invite_group_id)
        if invite_group:
            roster = [name.strip() for name in invite_group.guest_names.splitlines() if name.strip()]
    if not roster:
        roster = [name.strip() for name in (rsvp.attendee_names or "").splitlines() if name.strip()]
    if not roster and rsvp.guest_name:
        roster = [rsvp.guest_name]

    selected_names = (rsvp.attendee_names or "").splitlines()
    attendee_error = None
    if form.validate_on_submit():
        submitted_names = [name for name in request.form.getlist("attendee_names") if name.strip()]
        normalized_names = [" ".join(name.split()).casefold() for name in submitted_names]
        allowed_names = {" ".join(name.split()).casefold(): name for name in roster}
        if len(normalized_names) != len(set(normalized_names)) or any(name not in allowed_names for name in normalized_names):
            attendee_error = "Selecione somente nomes que pertencem a este convite."
            selected_names = submitted_names
        else:
            selected_names = [allowed_names[name] for name in normalized_names]
            rsvp.attendee_names = "\n".join(selected_names)
            rsvp.attendance = "yes" if selected_names else "no"
            rsvp.guest_count = len(selected_names)
            rsvp.message = (form.message.data or "").strip() or None
            db.session.commit()
            flash("Confirmação atualizada.", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/rsvp_form.html", form=form, rsvp=rsvp, roster=roster,
        selected_names=selected_names, attendee_error=attendee_error,
    )


@admin.post("/confirmacoes/<int:rsvp_id>/remover")
@login_required
def delete_rsvp(rsvp_id):
    rsvp = db.get_or_404(RSVP, rsvp_id)
    db.session.delete(rsvp)
    db.session.commit()
    flash("Resposta removida. O convite pode receber uma nova confirmação.", "success")
    return redirect(url_for("admin.dashboard"))


def _invite_reference_exists(reference_name, excluding_id=None):
    normalized = " ".join(reference_name.split()).casefold()
    return any(
        group.id != excluding_id and " ".join(group.reference_name.split()).casefold() == normalized
        for group in InviteGroup.query.all()
    )


def _public_invite_url(invite_group):
    # O endereco impresso nunca depende do Host da requisicao ou do servidor local.
    base_url = current_app.config["PUBLIC_SITE_URL"].rstrip("/")
    parsed = urlsplit(base_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        abort(503)
    if not invite_group.invite_token:
        abort(404)
    return base_url + url_for("main.rsvp", invite_token=invite_group.invite_token)


def _invite_qrcode_filename(invite_group):
    normalized = unicodedata.normalize("NFKD", invite_group.reference_name or "convite")
    safe_name = "".join(char for char in normalized if not unicodedata.combining(char))
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "-", safe_name).strip("-").lower()
    return f"{safe_name or 'convite'}-qrcode.png"


@admin.get("/convites/<int:group_id>/qrcode.png")
@login_required
def invite_qrcode(group_id):
    invite_group = db.get_or_404(InviteGroup, group_id)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=16, border=4)
    qr.add_data(_public_invite_url(invite_group))
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    output.seek(0)
    return send_file(
        output, mimetype="image/png", as_attachment=request.args.get("download") == "1",
        download_name=_invite_qrcode_filename(invite_group), max_age=0,
    )


@admin.get("/convites/<int:group_id>/imprimir")
@login_required
def print_invite_qrcode(group_id):
    invite_group = db.get_or_404(InviteGroup, group_id)
    return render_template(
        "admin/invite_qrcode.html", invite_group=invite_group,
        public_invite_url=_public_invite_url(invite_group),
    )


@admin.route("/convites/novo", methods=["GET", "POST"])
@login_required
def create_invite_group():
    form = InviteGroupForm()
    if form.validate_on_submit():
        if _invite_reference_exists(form.reference_name.data):
            form.reference_name.errors.append("Já existe um convite com esse nome de referência.")
        else:
            invite_group = InviteGroup(
                reference_name=form.reference_name.data,
                guest_names=form.guest_names.data,
            )
            db.session.add(invite_group)
            db.session.commit()
            flash("Convite cadastrado com sucesso.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/invite_group_form.html", form=form, page_title="Cadastrar convite")


@admin.route("/convites/<int:group_id>/editar", methods=["GET", "POST"])
@login_required
def edit_invite_group(group_id):
    invite_group = db.get_or_404(InviteGroup, group_id)
    form = InviteGroupForm(obj=invite_group)
    if form.validate_on_submit():
        if _invite_reference_exists(form.reference_name.data, excluding_id=invite_group.id):
            form.reference_name.errors.append("Já existe um convite com esse nome de referência.")
        else:
            invite_group.reference_name = form.reference_name.data
            invite_group.guest_names = form.guest_names.data
            db.session.commit()
            flash("Convite atualizado com sucesso.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/invite_group_form.html", form=form, page_title="Editar convite")


@admin.post("/convites/<int:group_id>/remover")
@login_required
def delete_invite_group(group_id):
    invite_group = db.get_or_404(InviteGroup, group_id)
    RSVP.query.filter_by(invite_group_id=invite_group.id).update(
        {RSVP.invite_group_id: None}, synchronize_session=False
    )
    db.session.delete(invite_group)
    db.session.commit()
    flash("Convite removido. As confirmações já recebidas foram preservadas.", "success")
    return redirect(url_for("admin.dashboard"))


@admin.post("/convites/<int:group_id>/renovar-link")
@login_required
def rotate_invite_token(group_id):
    invite_group = db.get_or_404(InviteGroup, group_id)
    invite_group.invite_token = token_urlsafe(24)
    db.session.commit()
    flash("Link privado renovado. O link anterior não funciona mais.", "success")
    return redirect(url_for("admin.dashboard"))


@admin.get("/confirmacoes.xlsx")
@login_required
def export_rsvps():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Confirmações"
    headers = ["Nome usado no convite", "Presença", "Total", "Pessoas confirmadas", "Mensagem", "Data da resposta"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="626348")

    attendance_labels = {"yes": "Sim", "no": "Não"}
    records = RSVP.query.order_by(RSVP.created_at.asc(), RSVP.id.asc()).all()
    for record in records:
        values = [
            record.guest_name,
            attendance_labels.get(record.attendance, record.attendance),
            record.guest_count,
            record.attendee_names or (
                "\n".join([record.guest_name] + (record.companion_names.splitlines() if record.companion_names else []))
                if record.attendance == "yes" else ""
            ),
            record.message or "",
            record.created_at.strftime("%d/%m/%Y %H:%M") if record.created_at else "",
        ]
        # Keep user-provided strings as literal cell values, never spreadsheet formulas.
        values = ["'" + value if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else value for value in values]
        sheet.append(values)

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in {"A": 30, "B": 14, "C": 10, "D": 42, "E": 48, "F": 22}.items():
        sheet.column_dimensions[column].width = width

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="confirmacoes-casamento.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@admin.route("/presentes/novo", methods=["GET", "POST"])
@login_required
def create_gift():
    form = GiftForm()
    if form.validate_on_submit():
        if form.gift_type.data == "honeymoon" and Gift.query.filter_by(gift_type="honeymoon").first():
            form.gift_type.errors.append("Já existe a cota para lua de mel. Edite esse item para trocar o link ou a descrição.")
            return render_template("admin/gift_form.html", form=form, page_title="Adicionar presente")
        image_filename = None
        if form.image.data and form.image.data.filename:
            try:
                image_filename = _save_gift_image(form.image.data)
            except ValueError as error:
                form.image.errors.append(str(error))
                return render_template("admin/gift_form.html", form=form, page_title="Adicionar presente")
        gift = Gift(
            title=form.title.data.strip(),
            description=(form.description.data or "").strip(),
            amount_cents=int(form.amount.data * 100) if form.amount.data is not None else 0,
            emoji=(form.emoji.data or "🎁").strip() or "🎁",
            gift_type=form.gift_type.data,
            external_url=(form.external_url.data or "").strip() or None,
            image_filename=image_filename,
        )
        db.session.add(gift)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            _delete_gift_image(image_filename)
            raise
        flash("Presente adicionado à lista.", "success")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/gift_form.html", form=form, page_title="Adicionar presente")


@admin.route("/presentes/<int:gift_id>/editar", methods=["GET", "POST"])
@login_required
def edit_gift(gift_id):
    gift = db.get_or_404(Gift, gift_id)
    form = GiftForm(obj=gift)
    if request.method == "GET":
        form.amount.data = gift.amount_cents / 100 if gift.amount_cents else None
    if form.validate_on_submit():
        other_honeymoon = Gift.query.filter_by(gift_type="honeymoon").filter(Gift.id != gift.id).first()
        if form.gift_type.data == "honeymoon" and other_honeymoon:
            form.gift_type.errors.append("Já existe a cota para lua de mel. Edite esse item para trocar o link ou a descrição.")
            return render_template("admin/gift_form.html", form=form, page_title="Editar presente", gift=gift)
        new_image_filename = None
        if form.image.data and form.image.data.filename:
            try:
                new_image_filename = _save_gift_image(form.image.data)
            except ValueError as error:
                form.image.errors.append(str(error))
                return render_template("admin/gift_form.html", form=form, page_title="Editar presente", gift=gift)
        old_image_filename = gift.image_filename
        gift.title = form.title.data.strip()
        gift.description = (form.description.data or "").strip()
        gift.amount_cents = int(form.amount.data * 100) if form.amount.data is not None else 0
        gift.emoji = (form.emoji.data or "🎁").strip() or "🎁"
        gift.gift_type = form.gift_type.data
        gift.external_url = (form.external_url.data or "").strip() or None
        if new_image_filename:
            gift.image_filename = new_image_filename
        elif form.remove_image.data:
            gift.image_filename = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            _delete_gift_image(new_image_filename)
            raise
        if old_image_filename and gift.image_filename != old_image_filename:
            _delete_gift_image(old_image_filename)
        flash("Presente atualizado.", "success")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/gift_form.html", form=form, page_title="Editar presente", gift=gift)


@admin.post("/presentes/<int:gift_id>/remover")
@login_required
def delete_gift(gift_id):
    gift = db.get_or_404(Gift, gift_id)
    image_filename = gift.image_filename
    db.session.delete(gift)
    db.session.commit()
    _delete_gift_image(image_filename)
    flash("Presente removido da lista.", "success")
    return redirect(url_for("admin.dashboard"))


@admin.post("/presentes/<int:gift_id>/cancelar-reserva")
@login_required
def cancel_gift_reservation(gift_id):
    gift = db.get_or_404(Gift, gift_id)
    if gift.gift_type not in ("reservation", "marketplace"):
        abort(404)

    result = db.session.execute(
        update(Gift)
        .where(Gift.id == gift_id, Gift.status == "reserved")
        .values(status="available", reserved_by=None, reserved_at=None)
    )
    db.session.commit()

    if result.rowcount == 1:
        flash("Reserva cancelada. O presente voltou a ficar disponível na lista.", "success")
    else:
        flash("Este presente não tem uma reserva ativa. Atualize o painel.", "error")
    return redirect(url_for("admin.dashboard"))
