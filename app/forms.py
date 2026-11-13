from flask_wtf import FlaskForm
from decimal import Decimal
from urllib.parse import urlsplit
from wtforms import StringField, SelectChoice, SelectField, TextAreaField, SubmitField, DecimalField, PasswordField, FileField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError
from flask_wtf.file import FileAllowed

class RSVPForm(FlaskForm):
    invite_code = StringField("Código privado do convite", validators=[
        DataRequired(message="Informe o código que acompanha seu convite."),
        Length(min=10, max=64, message="Confira o código privado do convite."),
    ])
    message = TextAreaField("Mensagem para os noivos (opcional)", validators=[
        Optional(), Length(max=500, message="A mensagem deve ter no máximo 500 caracteres."),
    ])
    submit = SubmitField("Enviar confirmação")


class InviteGroupForm(FlaskForm):
    reference_name = StringField("Nome usado no convite", validators=[
        DataRequired(message="Informe um nome de referência para o convite."),
        Length(min=2, max=120, message="O nome de referência deve ter entre 2 e 120 caracteres."),
    ])
    guest_names = TextAreaField("Nomes completos dos convidados", validators=[
        DataRequired(message="Cadastre pelo menos uma pessoa convidada."),
        Length(max=10000, message="A lista de convidados ficou muito longa."),
    ])
    submit = SubmitField("Salvar convite")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators=extra_validators)
        if self.reference_name.data:
            self.reference_name.data = " ".join(self.reference_name.data.split())
        if self.guest_names.data:
            names = [" ".join(name.split()) for name in self.guest_names.data.splitlines() if name.strip()]
            if not names:
                self.guest_names.errors.append("Cadastre pelo menos uma pessoa convidada.")
                valid = False
            elif any(len(name.split()) < 2 for name in names):
                self.guest_names.errors.append("Informe nome e sobrenome de cada convidado, um por linha.")
                valid = False
            elif any(len(name) > 120 for name in names):
                self.guest_names.errors.append("Cada nome deve ter no máximo 120 caracteres.")
                valid = False
            elif len({name.casefold() for name in names}) != len(names):
                self.guest_names.errors.append("Remova os nomes repetidos da lista.")
                valid = False
            else:
                self.guest_names.data = "\n".join(names)
        return valid

class ReserveGiftForm(FlaskForm):
    guest_name = StringField("Seu nome", validators=[
        DataRequired(message="Informe seu nome para escolher este presente."),
        Length(min=2, max=120, message="Digite um nome com pelo menos 2 caracteres."),
    ])
    submit = SubmitField("Escolher este presente")

class AdminLoginForm(FlaskForm):
    password = PasswordField("Senha administrativa", validators=[
        DataRequired(message="Digite a senha administrativa."),
        Length(max=256, message="A senha deve ter no máximo 256 caracteres."),
    ])
    submit = SubmitField("Entrar")


class AdminRSVPForm(FlaskForm):
    message = TextAreaField("Mensagem para os noivos (opcional)", validators=[
        Optional(), Length(max=500, message="A mensagem deve ter no máximo 500 caracteres."),
    ])
    submit = SubmitField("Salvar correção")

class GiftForm(FlaskForm):
    title = StringField("Nome do presente", validators=[
        DataRequired(message="Informe o nome do presente."),
        Length(max=120, message="O nome deve ter no máximo 120 caracteres."),
    ])
    description = StringField("Descrição", validators=[
        Optional(), Length(max=300, message="A descrição deve ter no máximo 300 caracteres."),
    ])
    gift_type = SelectField("Tipo", choices=[
        SelectChoice("reservation", "Presente com reserva"),
        SelectChoice("marketplace", "Produto em marketplace"),
        SelectChoice("honeymoon", "Cota para lua de mel"),
    ], validators=[DataRequired(message="Selecione o tipo do presente.")])
    amount = DecimalField("Preço aproximado em reais (opcional)", places=2, validators=[
        Optional(), NumberRange(min=Decimal("0.01"), max=Decimal("999999.99"), message="Informe um valor entre R$ 0,01 e R$ 999.999,99."),
    ])
    external_url = StringField("Link do produto ou do Mercado Pago", validators=[
        Optional(), Length(max=1000, message="O link deve ter no máximo 1.000 caracteres."),
    ])
    emoji = StringField("Ícone (emoji)", validators=[
        Optional(), Length(max=12, message="O ícone deve ter no máximo 12 caracteres."),
    ])
    image = FileField("Imagem do produto", validators=[
        Optional(), FileAllowed(["png", "jpg", "jpeg", "webp"], "Envie uma imagem PNG, JPG, JPEG ou WebP."),
    ])
    remove_image = BooleanField("Remover imagem atual")
    submit = SubmitField("Salvar presente")

    def validate_external_url(self, field):
        value = (field.data or "").strip()
        if not value:
            return
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError("Informe um link completo começando com https://.")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators=extra_validators)
        if self.gift_type.data == "marketplace" and not (self.external_url.data or "").strip():
            self.external_url.errors.append("Informe o link direto para o produto no marketplace.")
            valid = False
        return valid
