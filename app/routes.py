from pathlib import Path
from datetime import datetime, timezone
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy import update
from .extensions import db
from .models import Gift, InviteGroup, RSVP
from .forms import RSVPForm, ReserveGiftForm
from .payment_options import HONEYMOON_CREDIT_OPTIONS, HONEYMOON_PIX_OPTIONS

main = Blueprint("main", __name__)

PRODUCT_IMAGES = {
    "https://a.co/d/0gGuAo8p": "presentes/jogo-toalha.png",
    "https://a.co/d/03jbW8Ei": "presentes/garrafa-termica.png",
    "https://www.havan.com.br/jogo-de-assadeiras-retangular-portuguesa-havan-casa-3-pecas-branco/p": "presentes/jogo-assadeira.png",
}

def normalize_name(value):
    return " ".join((value or "").split()).casefold()

def guest_names_from_group(group):
    return [" ".join(name.split()) for name in group.guest_names.splitlines() if name.strip()]

@main.get("/")
def index():
    gifts = Gift.query.filter(Gift.gift_type != "honeymoon").order_by(Gift.id.asc()).all()
    available_count = Gift.query.filter_by(status="available", gift_type="reservation").count()
    return render_template("index.html", gifts=gifts, available_count=available_count,
                           product_images=PRODUCT_IMAGES, rsvp_form=RSVPForm(), reserve_form=ReserveGiftForm(),
                           reserve_error_gift_id=None,
                           reservation_success_gift_id=session.pop("reservation_success_gift_id", None))

@main.get("/lua-de-mel")
def honeymoon():
    image_dir = Path(current_app.static_folder) / "img"
    photo = next((name for name in ("lua-de-mel.webp", "lua-de-mel.jpg", "lua-de-mel.jpeg", "lua-de-mel.png") if (image_dir / name).is_file()), None)
    return render_template("honeymoon.html", honeymoon_photo=photo, pix_options=HONEYMOON_PIX_OPTIONS, credit_options=HONEYMOON_CREDIT_OPTIONS)

@main.get("/imagens/presentes/<path:filename>")
def gift_image(filename):
    return send_from_directory(current_app.config["GIFT_UPLOAD_FOLDER"], filename)

@main.post("/convites/consultar")
def lookup_invite():
    invite_token = request.form.get("codigo", "").strip()
    if len(invite_token) < 10 or len(invite_token) > 64:
        return jsonify(found=False), 400
    invite_group = InviteGroup.query.filter_by(invite_token=invite_token).first()
    if not invite_group:
        response = jsonify(found=False)
    else:
        already_responded = RSVP.query.filter_by(invite_group_id=invite_group.id).first() is not None
        response = jsonify(
            found=True,
            guests=guest_names_from_group(invite_group),
            already_responded=already_responded,
        )
    response.headers["Cache-Control"] = "no-store"
    return response

@main.route("/confirmar-presenca", defaults={"invite_token": None}, methods=["GET", "POST"])
@main.route("/confirmar-presenca/<string:invite_token>", methods=["GET", "POST"])
def rsvp(invite_token):
    form = RSVPForm()
    invite_group = None
    invite_guest_names = []
    selected_guest_names = []
    attendee_errors = []
    invite_already_responded = False

    # O token da rota e a fonte confiável do QR Code. Também o mantém no
    # formulário durante o POST, caso o navegador não envie o campo visível.
    if invite_token:
        form.invite_code.data = invite_token
    submitted_code = (form.invite_code.data or "").strip()
    if submitted_code:
        candidate = InviteGroup.query.filter_by(invite_token=submitted_code).first()
        if candidate:
            invite_group = candidate
            invite_guest_names = guest_names_from_group(invite_group)
            if request.method == "POST":
                selected_guest_names = request.form.getlist("attendee_names")
            invite_already_responded = RSVP.query.filter_by(invite_group_id=invite_group.id).first() is not None

    if form.validate_on_submit():
        if not invite_group:
            form.invite_code.errors.append("Não encontramos esse código de convite. Confira o link recebido com os noivos.")
            return render_template(
                "rsvp.html", form=form, invite_group=None, invite_guest_names=[],
                selected_guest_names=[], attendee_errors=[], invite_already_responded=False,
            )

        if invite_already_responded:
            form.invite_code.errors.append("Este convite já enviou uma confirmação. Se precisar corrigir a resposta, fale com os noivos.")
            return render_template(
                "rsvp.html", form=form, invite_group=invite_group,
                invite_guest_names=invite_guest_names,
                selected_guest_names=selected_guest_names, attendee_errors=[],
                invite_already_responded=True,
            ), 409

        available_names = {normalize_name(name): name for name in invite_guest_names}
        submitted_names = [name for name in request.form.getlist("attendee_names") if name.strip()]
        normalized_names = [normalize_name(name) for name in submitted_names]
        if len(set(normalized_names)) != len(normalized_names) or any(name not in available_names for name in normalized_names):
            attendee_errors.append("Selecione somente os nomes que aparecem na lista deste convite.")
            return render_template(
                "rsvp.html", form=form, invite_group=invite_group,
                invite_guest_names=invite_guest_names, selected_guest_names=[],
                attendee_errors=attendee_errors,
            )

        selected_guest_names = [available_names[name] for name in normalized_names]
        record = RSVP(
            guest_name=invite_group.reference_name,
            email="",
            invite_group_id=invite_group.id,
            attendance="yes" if selected_guest_names else "no",
            guest_count=len(selected_guest_names),
            attendee_names="\n".join(selected_guest_names),
            invite_guest_names="\n".join(invite_guest_names),
            message=(form.message.data or "").strip() or None,
        )
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.invite_code.errors.append("Este convite já enviou uma confirmação. Se precisar corrigir a resposta, fale com os noivos.")
            return render_template(
                "rsvp.html", form=form, invite_group=invite_group,
                invite_guest_names=invite_guest_names,
                selected_guest_names=selected_guest_names, attendee_errors=[],
                invite_already_responded=True,
            ), 409
        flash("Sua resposta foi registrada. Obrigado!", "success")
        return redirect(url_for("main.rsvp", invite_token=invite_group.invite_token))
    return render_template(
        "rsvp.html", form=form, invite_group=invite_group,
        invite_guest_names=invite_guest_names,
        selected_guest_names=selected_guest_names, attendee_errors=attendee_errors,
        invite_already_responded=invite_already_responded,
    )

@main.post("/presentes/<int:gift_id>/reservar")
def reserve_gift(gift_id):
    gift = db.get_or_404(Gift, gift_id)
    if gift.gift_type not in ("reservation", "marketplace"):
        abort(404)
    form = ReserveGiftForm()
    if not form.validate_on_submit():
        if not form.guest_name.errors:
            form.guest_name.errors.append("Não foi possível validar o envio. Atualize a página e tente novamente.")
        gifts = Gift.query.filter(Gift.gift_type != "honeymoon").order_by(Gift.id.asc()).all()
        available_count = Gift.query.filter_by(status="available", gift_type="reservation").count()
        return render_template(
            "index.html",
            gifts=gifts,
            available_count=available_count,
            product_images=PRODUCT_IMAGES,
            rsvp_form=RSVPForm(),
            reserve_form=form,
            reserve_error_gift_id=gift.id,
        ), 400

    # Atualização condicional evita que duas pessoas reservem o mesmo item simultaneamente.
    result = db.session.execute(
        update(Gift)
        .where(Gift.id == gift_id, Gift.status == "available")
        .values(status="reserved", reserved_by=form.guest_name.data.strip(), reserved_at=datetime.now(timezone.utc))
    )
    db.session.commit()

    if result.rowcount == 1:
        session["reservation_success_gift_id"] = gift.id
        return redirect(url_for("main.index") + "#presentes")

    flash("Esse presente já foi escolhido. Que tal selecionar outro?", "error")
    return redirect(url_for("main.index") + "#presentes")

@main.get("/health")
def health():
    return {"status": "ok"}
