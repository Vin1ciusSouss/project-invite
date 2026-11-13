import unittest
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import load_workbook
from PIL import Image
from sqlalchemy import inspect, text
from flask_migrate import upgrade
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Gift, InviteGroup, RSVP


class WeddingSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_password = "Senha-forte-de-teste-2026"
        cls.image_tempdir = TemporaryDirectory()
        cls.app = create_app({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "chave-apenas-para-testes",
            "ADMIN_PASSWORD_HASH": generate_password_hash(cls.admin_password),
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "GIFT_UPLOAD_FOLDER": cls.image_tempdir.name,
        })

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        cls.image_tempdir.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            db.session.add_all([
                Gift(
                    title="Jogo de toalhas",
                    description="Presente físico",
                    gift_type="marketplace",
                    external_url="https://example.com/toalhas",
                    emoji="🎁",
                ),
                Gift(
                    title="Cafeteira",
                    description="Presente com reserva",
                    gift_type="reservation",
                    emoji="☕",
                ),
                Gift(
                    title="Cota para lua de mel",
                    description="Escolha o valor da cota",
                    gift_type="honeymoon",
                    external_url="https://example.com/pagamento",
                    emoji="🌴",
                ),
            ])
            db.session.add(InviteGroup(
                reference_name="Pessoa Responsável",
                guest_names="Pessoa Responsável\nConvidado Sobrenome\nTerceira Pessoa",
            ))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()

    def submit_rsvp(self, **overrides):
        with self.app.app_context():
            invite_token = db.session.get(InviteGroup, 1).invite_token
        data = {
            "invite_code": invite_token,
            "attendee_names": ["Pessoa Responsável", "Convidado Sobrenome"],
            "message": "Até lá!",
        }
        data.update(overrides)
        return self.client.post("/confirmar-presenca", data=data)

    def login_admin(self):
        return self.client.post("/admin/login", data={"password": self.admin_password})

    @staticmethod
    def close_upload_response(response):
        input_stream = response.request.environ.get("wsgi.input")
        if input_stream and hasattr(input_stream, "close"):
            input_stream.close()
        response.close()

    @staticmethod
    def image_bytes(image_format):
        output = BytesIO()
        Image.new("RGB", (8, 8), (120, 140, 110)).save(output, format=image_format)
        return output.getvalue()

    def test_home_displays_gifts_and_event(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Lista de presentes".encode(), response.data)
        self.assertIn("Jogo de toalhas".encode(), response.data)
        self.assertIn("Cafeteira".encode(), response.data)

    def test_honeymoon_page_displays_payment_link_and_photo(self):
        response = self.client.get("/lua-de-mel")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"https://mpago.la/1VRGRuo", response.data)
        self.assertNotIn(b"https://example.com/pagamento", response.data)
        self.assertIn(b"img/lua-de-mel.png", response.data)

    def test_honeymoon_displays_fixed_pix_options_separately_from_credit(self):
        response = self.client.get("/lua-de-mel")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"R$ 150,00", response.data)
        self.assertIn(b"R$ 200,00", response.data)
        self.assertIn(b'href="https://nubank.com.br/cobrar/4d48g/6af64055-adbc-4209-9d15-8a184b78b4ae"', response.data)
        self.assertIn(b'href="https://nubank.com.br/cobrar/4d48g/6af64074-528e-4b87-a49e-8f131df3937b"', response.data)
        self.assertIn("Presentear com cartão".encode(), response.data)
        self.assertIn(b'href="https://mpago.la/1VRGRuo"', response.data)
        self.assertIn(b'href="https://mpago.la/2somgxF"', response.data)
        self.assertNotIn(b'href="https://example.com/pagamento"', response.data)
        self.assertNotIn("Prefere outro valor no cartão?".encode(), response.data)

    def test_honeymoon_fixed_amounts_remain_available_without_open_value_link(self):
        with self.app.app_context():
            gift = Gift.query.filter_by(gift_type="honeymoon").one()
            gift.external_url = None
            db.session.commit()
        response = self.client.get("/lua-de-mel")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"R$ 150,00", response.data)
        self.assertIn(b"R$ 200,00", response.data)
        self.assertIn(b'href="https://mpago.la/1VRGRuo"', response.data)
        self.assertIn(b'href="https://mpago.la/2somgxF"', response.data)
        self.assertNotIn("Prefere outro valor no cartão?".encode(), response.data)

    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_http_errors_share_logo_and_preserve_status_and_headers(self):
        missing = self.client.get("/pagina-inexistente")
        self.assertEqual(missing.status_code, 404)
        self.assertIn(b"monograma-ve.png", missing.data)
        self.assertIn(b"favicon-ve-dourado.svg", missing.data)
        self.assertIn("Página não encontrada".encode(), missing.data)
        wrong_method = self.client.post("/health")
        self.assertEqual(wrong_method.status_code, 405)
        self.assertIn("GET", wrong_method.headers["Allow"])
        self.assertIn(b"monograma-ve.png", wrong_method.data)

    def test_production_requires_a_configured_secret_key(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY forte"):
                create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})

    def test_production_requires_an_admin_password_hash(self):
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "SECRET_KEY": "test-secret-key-that-is-not-used",
            "ADMIN_PASSWORD_HASH": "",
        }):
            with self.assertRaisesRegex(RuntimeError, "ADMIN_PASSWORD_HASH"):
                create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})

    def test_invite_lookup_requires_csrf_protection(self):
        with self.app.app_context():
            invite_token = db.session.get(InviteGroup, 1).invite_token
        self.app.config["WTF_CSRF_ENABLED"] = True
        try:
            response = self.client.post("/convites/consultar", data={"codigo": invite_token})
            page = self.client.get("/confirmar-presenca")
            token_match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data)
            self.assertIsNotNone(token_match)
            valid_request = self.client.post("/convites/consultar", data={
                "codigo": invite_token,
                "csrf_token": token_match.group(1).decode(),
            })
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = False
        self.assertEqual(response.status_code, 400)
        self.assertEqual(valid_request.status_code, 200)
        self.assertTrue(valid_request.json["found"])

    def test_https_login_accepts_same_origin_and_keeps_csrf_protection(self):
        original_csrf = self.app.config["WTF_CSRF_ENABLED"]
        original_secure = self.app.config["SESSION_COOKIE_SECURE"]
        self.app.config.update(WTF_CSRF_ENABLED=True, SESSION_COOKIE_SECURE=True)
        try:
            origin = "https://viniciussouss.pythonanywhere.com"
            page = self.client.get("/admin/login", base_url=origin)
            self.assertEqual(page.headers["Referrer-Policy"], "same-origin")
            token = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data).group(1).decode()
            data = {"password": self.admin_password, "csrf_token": token}
            missing_referrer = self.client.post("/admin/login", base_url=origin, data=data)
            self.assertEqual(missing_referrer.status_code, 400)
            foreign_referrer = self.client.post("/admin/login", base_url=origin, data=data, headers={"Referer": "https://other.example.com/"})
            self.assertEqual(foreign_referrer.status_code, 400)
            missing_token = self.client.post("/admin/login", base_url=origin, data={"password": self.admin_password}, headers={"Referer": origin + "/admin/login"})
            self.assertEqual(missing_token.status_code, 400)
            valid = self.client.post("/admin/login", base_url=origin, data=data, headers={"Referer": origin + "/admin/login"})
            self.assertEqual(valid.status_code, 302)
            self.assertEqual(self.client.get("/admin/", base_url=origin).status_code, 200)
        finally:
            self.app.config.update(WTF_CSRF_ENABLED=original_csrf, SESSION_COOKIE_SECURE=original_secure)

    def test_migration_adds_private_tokens_to_legacy_invite_groups(self):
        legacy_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        with legacy_app.app_context():
            with db.engine.begin() as connection:
                connection.execute(text("CREATE TABLE invite_group (id INTEGER PRIMARY KEY, reference_name VARCHAR(120) NOT NULL UNIQUE, guest_names TEXT NOT NULL)"))
                connection.execute(text("INSERT INTO invite_group (reference_name, guest_names) VALUES ('Convite legado', 'Pessoa Um')"))
            upgrade()
            invite_token = db.session.execute(text("SELECT invite_token FROM invite_group WHERE id = 1")).scalar_one()
            self.assertEqual(len(invite_token), 32)
            self.assertIn("uq_invite_group_token", {index["name"] for index in inspect(db.engine).get_indexes("invite_group")})
            db.session.remove()
            db.engine.dispose()

    def test_production_enables_secure_session_cookie(self):
        production_hash = generate_password_hash("Senha-apenas-para-testar-configuracao")
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "SECRET_KEY": "test-secret-key-that-is-not-used",
            "ADMIN_PASSWORD_HASH": production_hash,
            "SESSION_COOKIE_SECURE": "false",
        }):
            production_app = create_app({
                "TESTING": True,
                "WTF_CSRF_ENABLED": False,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            })
        self.assertTrue(production_app.config["SESSION_COOKIE_SECURE"])
        self.assertEqual(production_app.config["PREFERRED_URL_SCHEME"], "https")
        with production_app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_rsvp_page_has_conditional_name_list(self):
        response = self.client.get("/confirmar-presenca")
        self.assertEqual(response.status_code, 200)
        self.assertIn("invite-guest-list".encode(), response.data)
        self.assertIn("attendee_names".encode(), response.data)
        self.assertIn("/convites/consultar".encode(), response.data)
        self.assertNotIn("E-mail".encode(), response.data)
        self.assertNotIn("guest_count".encode(), response.data)

    def test_invite_lookup_requires_private_token(self):
        with self.app.app_context():
            invite_token = db.session.get(InviteGroup, 1).invite_token
        found = self.client.post("/convites/consultar", data={"codigo": invite_token})
        self.assertEqual(found.status_code, 200)
        self.assertTrue(found.json["found"])
        self.assertEqual(found.json["guests"], ["Pessoa Responsável", "Convidado Sobrenome", "Terceira Pessoa"])
        missing = self.client.post("/convites/consultar", data={"codigo": "codigo-invalido-123"})
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.json["found"])
        self.assertEqual(found.headers["Cache-Control"], "no-store")

    def test_private_invite_link_reveals_only_its_roster(self):
        with self.app.app_context():
            invite_token = db.session.get(InviteGroup, 1).invite_token
        generic_page = self.client.get("/confirmar-presenca")
        self.assertNotIn("Terceira Pessoa".encode(), generic_page.data)
        private_page = self.client.get(f"/confirmar-presenca/{invite_token}")
        self.assertEqual(private_page.status_code, 200)
        self.assertIn("Terceira Pessoa".encode(), private_page.data)
        self.assertEqual(private_page.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(private_page.headers["Cache-Control"], "no-store")

    def test_yes_rsvp_saves_normalized_names_and_derived_total(self):
        response = self.submit_rsvp(attendee_names=["Pessoa Responsável", "Convidado Sobrenome"])
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            record = RSVP.query.one()
            self.assertEqual(record.attendance, "yes")
            self.assertEqual(record.attendee_names, "Pessoa Responsável\nConvidado Sobrenome")
            self.assertEqual(record.guest_count, 2)
            self.assertEqual(record.message, "Até lá!")

    def test_empty_selection_records_that_no_one_is_attending(self):
        response = self.submit_rsvp(attendee_names=[])
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            record = RSVP.query.one()
            self.assertEqual(record.attendance, "no")
            self.assertEqual(record.guest_count, 0)
            self.assertEqual(record.attendee_names, "")

    def test_rsvp_rejects_name_not_in_invite_group(self):
        response = self.submit_rsvp(attendee_names=["Pessoa Responsável", "Pessoa Não Convidada"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("Selecione somente os nomes que aparecem".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(RSVP.query.count(), 0)

    def test_rsvp_rejects_invalid_private_invite_code(self):
        response = self.submit_rsvp(invite_code="codigo-de-outro-convite")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Não encontramos esse código de convite".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(RSVP.query.count(), 0)

    def test_invite_group_can_submit_only_one_response(self):
        self.submit_rsvp()
        response = self.submit_rsvp(attendee_names=["Pessoa Responsável", "Convidado Sobrenome"])
        self.assertEqual(response.status_code, 409)
        self.assertIn("Este convite já enviou uma confirmação".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(RSVP.query.count(), 1)

    def test_lookup_indicates_when_invite_already_responded(self):
        self.submit_rsvp()
        with self.app.app_context():
            invite_token = db.session.get(InviteGroup, 1).invite_token
        response = self.client.post("/convites/consultar", data={"codigo": invite_token})
        self.assertTrue(response.json["already_responded"])

    def test_reservation_requires_name_and_shows_error_near_field(self):
        response = self.client.post("/presentes/1/reservar", data={"guest_name": "A"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Digite um nome com pelo menos 2 caracteres".encode(), response.data)
        self.assertIn('aria-invalid="true"'.encode(), response.data)
        with self.app.app_context():
            self.assertEqual(db.session.get(Gift, 1).status, "available")

    def test_reservation_records_guest_name(self):
        response = self.client.post("/presentes/2/reservar", data={"guest_name": "Convidado Exemplo"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            gift = db.session.get(Gift, 2)
            self.assertEqual(gift.status, "reserved")
            self.assertEqual(gift.reserved_by, "Convidado Exemplo")

    def test_successful_reservation_message_appears_inside_gift_card(self):
        response = self.client.post(
            "/presentes/1/reservar",
            data={"guest_name": "Convidado Exemplo"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Reserva registrada. A compra deve ser finalizada diretamente na loja.".encode(), response.data)
        self.assertNotIn('class="flash success"'.encode(), response.data)

    def test_reserved_gift_cannot_be_reserved_twice(self):
        self.client.post("/presentes/2/reservar", data={"guest_name": "Primeira Pessoa"})
        response = self.client.post("/presentes/2/reservar", data={"guest_name": "Segunda Pessoa"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Esse presente já foi escolhido".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(db.session.get(Gift, 2).reserved_by, "Primeira Pessoa")

    def test_honeymoon_gift_cannot_be_reserved_from_physical_list(self):
        response = self.client.post("/presentes/3/reservar", data={"guest_name": "Convidado Exemplo"})
        self.assertEqual(response.status_code, 404)

    def test_admin_routes_require_authentication(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])
        response = self.client.get("/admin/confirmacoes.xlsx")
        self.assertEqual(response.status_code, 302)

    def test_admin_login_rejects_wrong_password_and_accepts_correct_password(self):
        wrong = self.client.post("/admin/login", data={"password": "senha errada"})
        self.assertEqual(wrong.status_code, 200)
        self.assertIn("senha ou a configuração".encode(), wrong.data)
        correct = self.login_admin()
        self.assertEqual(correct.status_code, 302)
        self.assertIn("/admin/", correct.headers["Location"])

    def test_admin_dashboard_shows_rsvps_names_and_totals(self):
        self.submit_rsvp(attendee_names=["Pessoa Responsável", "Convidado Sobrenome"])
        self.login_admin()
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Pessoas confirmadas".encode(), response.data)
        self.assertIn("Terceira Pessoa".encode(), response.data)
        self.assertIn("Confirmou".encode(), response.data)
        self.assertIn("Não confirmou".encode(), response.data)
        self.assertIn(b">2</strong>", response.data)

    def test_admin_can_renew_private_invite_link(self):
        with self.app.app_context():
            original_token = db.session.get(InviteGroup, 1).invite_token
        self.login_admin()
        dashboard = self.client.get("/admin/")
        self.assertIn("Copiar link".encode(), dashboard.data)
        response = self.client.post("/admin/convites/1/renovar-link")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            renewed_token = db.session.get(InviteGroup, 1).invite_token
        self.assertNotEqual(original_token, renewed_token)
        old_link = self.client.post("/convites/consultar", data={"codigo": original_token})
        new_link = self.client.post("/convites/consultar", data={"codigo": renewed_token})
        self.assertFalse(old_link.json["found"])
        self.assertTrue(new_link.json["found"])

    def test_admin_can_correct_rsvp_and_recalculate_attendance(self):
        self.submit_rsvp()
        self.login_admin()
        with self.app.app_context():
            rsvp_id = RSVP.query.one().id

        page = self.client.get(f"/admin/confirmacoes/{rsvp_id}/editar")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Corrigir confirmação".encode(), page.data)
        updated = self.client.post(f"/admin/confirmacoes/{rsvp_id}/editar", data={
            "attendee_names": ["Terceira Pessoa"],
            "message": "Atualização pelo painel",
        })
        self.assertEqual(updated.status_code, 302)
        with self.app.app_context():
            rsvp = db.session.get(RSVP, rsvp_id)
            self.assertEqual(rsvp.attendance, "yes")
            self.assertEqual(rsvp.guest_count, 1)
            self.assertEqual(rsvp.attendee_names, "Terceira Pessoa")
            self.assertEqual(rsvp.message, "Atualização pelo painel")

        absent = self.client.post(f"/admin/confirmacoes/{rsvp_id}/editar", data={"message": "Não iremos"})
        self.assertEqual(absent.status_code, 302)
        with self.app.app_context():
            rsvp = db.session.get(RSVP, rsvp_id)
            self.assertEqual(rsvp.attendance, "no")
            self.assertEqual(rsvp.guest_count, 0)
            self.assertEqual(rsvp.attendee_names, "")

    def test_admin_can_remove_response_and_reopen_the_same_invite(self):
        self.submit_rsvp()
        self.login_admin()
        with self.app.app_context():
            rsvp_id = RSVP.query.one().id
            original_token = db.session.get(InviteGroup, 1).invite_token
        page = self.client.get("/admin/")
        self.assertNotIn("Baixar Excel".encode(), page.data)
        self.assertIn("Corrigir resposta".encode(), page.data)
        self.assertIn(b'id="delete-rsvp-dialog"', page.data)
        response = self.client.post(f"/admin/confirmacoes/{rsvp_id}/remover", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Aguardando".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(RSVP.query.count(), 0)
            self.assertEqual(db.session.get(InviteGroup, 1).invite_token, original_token)
        lookup = self.client.post("/convites/consultar", data={"codigo": original_token})
        self.assertFalse(lookup.json["already_responded"])
        self.assertEqual(self.submit_rsvp(attendee_names=["Terceira Pessoa"]).status_code, 302)
        with self.app.app_context():
            self.assertEqual(RSVP.query.one().attendee_names, "Terceira Pessoa")

    def test_removing_one_response_preserves_other_responses_and_gifts(self):
        self.submit_rsvp()
        with self.app.app_context():
            first_id = RSVP.query.one().id
            other_group = InviteGroup(reference_name="Outro convite", guest_names="Outra Pessoa")
            db.session.add(other_group)
            db.session.flush()
            db.session.add(RSVP(guest_name="Outro convite", email="", attendance="yes", invite_group_id=other_group.id, guest_count=1, attendee_names="Outra Pessoa", invite_guest_names="Outra Pessoa"))
            gift = db.session.get(Gift, 1)
            gift.status = "reserved"
            gift.reserved_by = "Pessoa Responsável"
            db.session.commit()
        self.login_admin()
        self.assertEqual(self.client.post(f"/admin/confirmacoes/{first_id}/remover").status_code, 302)
        with self.app.app_context():
            self.assertEqual(RSVP.query.one().guest_name, "Outro convite")
            self.assertEqual(InviteGroup.query.count(), 2)
            self.assertEqual(db.session.get(Gift, 1).status, "reserved")

    def test_removing_response_requires_authentication_post_and_csrf(self):
        self.submit_rsvp()
        with self.app.app_context():
            rsvp_id = RSVP.query.one().id
        endpoint = f"/admin/confirmacoes/{rsvp_id}/remover"
        self.assertEqual(self.client.post(endpoint).status_code, 302)
        self.assertEqual(self.client.get(endpoint).status_code, 405)
        self.login_admin()
        original_csrf = self.app.config["WTF_CSRF_ENABLED"]
        self.app.config["WTF_CSRF_ENABLED"] = True
        try:
            self.assertEqual(self.client.post(endpoint).status_code, 400)
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = original_csrf
        with self.app.app_context():
            self.assertEqual(RSVP.query.count(), 1)

    def test_admin_can_export_rsvps_to_excel(self):
        self.submit_rsvp()
        self.login_admin()
        response = self.client.get("/admin/confirmacoes.xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml".encode(), response.content_type.encode())
        workbook = load_workbook(BytesIO(response.data), read_only=True)
        sheet = workbook["Confirmações"]
        self.assertEqual(sheet.cell(1, 4).value, "Pessoas confirmadas")
        self.assertEqual(sheet.cell(2, 3).value, 2)
        self.assertIn("Convidado Sobrenome", sheet.cell(2, 4).value)
        workbook.close()

    def test_admin_can_create_edit_and_delete_gift(self):
        self.login_admin()
        created = self.client.post("/admin/presentes/novo", data={
            "title": "Jogo de pratos",
            "description": "Louça para a casa",
            "gift_type": "reservation",
            "amount": "",
            "external_url": "",
            "emoji": "🎁",
        })
        self.assertEqual(created.status_code, 302)
        with self.app.app_context():
            gift = Gift.query.filter_by(title="Jogo de pratos").one()
            gift_id = gift.id

        updated = self.client.post(f"/admin/presentes/{gift_id}/editar", data={
            "title": "Jogo de pratos atualizado",
            "description": "Nova descrição",
            "gift_type": "reservation",
            "amount": "",
            "external_url": "",
            "emoji": "🍽️",
        })
        self.assertEqual(updated.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.get(Gift, gift_id).title, "Jogo de pratos atualizado")

        deleted = self.client.post(f"/admin/presentes/{gift_id}/remover")
        self.assertEqual(deleted.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Gift, gift_id))

    def test_admin_can_upload_replace_and_remove_product_image(self):
        self.login_admin()
        png_data = self.image_bytes("PNG")
        created = self.client.post("/admin/presentes/novo", data={
            "title": "Presente com imagem",
            "description": "Imagem enviada pelo painel",
            "gift_type": "marketplace",
            "amount": "",
            "external_url": "https://example.com/produto",
            "emoji": "🎁",
            "image": (BytesIO(png_data), "produto.png"),
        })
        self.assertEqual(created.status_code, 302)
        with self.app.app_context():
            gift = Gift.query.filter_by(title="Presente com imagem").one()
            gift_id = gift.id
            old_image = gift.image_filename
        old_path = Path(self.image_tempdir.name) / old_image
        self.assertTrue(old_path.is_file())
        with Image.open(old_path) as saved_image:
            self.assertEqual(saved_image.format, "PNG")
            self.assertEqual(saved_image.size, (8, 8))
        self.assertIn(old_image.encode(), self.client.get("/").data)
        uploaded_image_response = self.client.get(f"/imagens/presentes/{old_image}")
        self.assertEqual(uploaded_image_response.status_code, 200)
        uploaded_image_response.close()

        jpeg_data = self.image_bytes("JPEG")
        replaced = self.client.post(f"/admin/presentes/{gift_id}/editar", data={
            "title": "Presente com imagem",
            "description": "Imagem atualizada",
            "gift_type": "marketplace",
            "amount": "",
            "external_url": "https://example.com/produto",
            "emoji": "🎁",
            "image": (BytesIO(jpeg_data), "produto.jpg"),
        })
        self.assertEqual(replaced.status_code, 302)
        self.assertFalse(old_path.exists())
        with self.app.app_context():
            current_image = db.session.get(Gift, gift_id).image_filename
        self.assertTrue((Path(self.image_tempdir.name) / current_image).is_file())

        removed = self.client.post(f"/admin/presentes/{gift_id}/editar", data={
            "title": "Presente com imagem",
            "description": "Sem imagem",
            "gift_type": "marketplace",
            "amount": "",
            "external_url": "https://example.com/produto",
            "emoji": "🎁",
            "remove_image": "y",
        })
        self.assertEqual(removed.status_code, 302)
        self.assertFalse((Path(self.image_tempdir.name) / current_image).exists())
        with self.app.app_context():
            self.assertIsNone(db.session.get(Gift, gift_id).image_filename)
        self.close_upload_response(created)
        self.close_upload_response(replaced)
        self.close_upload_response(removed)

    def test_admin_rejects_file_with_image_extension_but_invalid_content(self):
        self.login_admin()
        response = self.client.post("/admin/presentes/novo", data={
            "title": "Arquivo inválido",
            "description": "",
            "gift_type": "reservation",
            "amount": "",
            "external_url": "",
            "emoji": "🎁",
            "image": (BytesIO(b"not an image"), "fake.png"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("não contém uma imagem válida".encode(), response.data)
        with self.app.app_context():
            self.assertIsNone(Gift.query.filter_by(title="Arquivo inválido").first())
        self.close_upload_response(response)

    def test_admin_rejects_product_image_larger_than_five_megabytes(self):
        self.login_admin()
        response = self.client.post("/admin/presentes/novo", data={
            "title": "Imagem muito grande",
            "description": "",
            "gift_type": "reservation",
            "amount": "",
            "external_url": "",
            "emoji": "🎁",
            "image": (BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "grande.png"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("no máximo 5 MB".encode(), response.data)
        self.close_upload_response(response)

    def test_admin_can_create_and_edit_invite_group(self):
        self.login_admin()
        created = self.client.post("/admin/convites/novo", data={
            "reference_name": "Família Silva",
            "guest_names": "Ana Silva\nBruno Silva",
        })
        self.assertEqual(created.status_code, 302)
        with self.app.app_context():
            invite_group = InviteGroup.query.filter_by(reference_name="Família Silva").one()
            group_id = invite_group.id
            self.assertEqual(invite_group.guest_names, "Ana Silva\nBruno Silva")

        edited = self.client.post(f"/admin/convites/{group_id}/editar", data={
            "reference_name": "Família Silva",
            "guest_names": "Ana Silva\nBruno Silva\nCarla Silva",
        })
        self.assertEqual(edited.status_code, 302)
        with self.app.app_context():
            invite_group = InviteGroup.query.filter_by(reference_name="Família Silva").one()
            invite_token = invite_group.invite_token
        lookup = self.client.post("/convites/consultar", data={"codigo": invite_token})
        self.assertEqual(lookup.json["guests"], ["Ana Silva", "Bruno Silva", "Carla Silva"])

    def test_admin_rejects_duplicate_invite_reference_and_guest_names(self):
        self.login_admin()
        duplicate_reference = self.client.post("/admin/convites/novo", data={
            "reference_name": " pessoa responsável ",
            "guest_names": "Ana Silva",
        })
        self.assertEqual(duplicate_reference.status_code, 200)
        self.assertIn("Já existe um convite com esse nome".encode(), duplicate_reference.data)

        duplicate_guest = self.client.post("/admin/convites/novo", data={
            "reference_name": "Novo convite",
            "guest_names": "Ana Silva\nana   silva",
        })
        self.assertEqual(duplicate_guest.status_code, 200)
        self.assertIn("Remova os nomes repetidos".encode(), duplicate_guest.data)

    def test_admin_can_remove_invite_group_without_deleting_rsvp(self):
        self.submit_rsvp()
        self.login_admin()
        response = self.client.post("/admin/convites/1/remover")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            record = RSVP.query.one()
            self.assertIsNone(record.invite_group_id)
            self.assertEqual(record.attendee_names, "Pessoa Responsável\nConvidado Sobrenome")
            self.assertEqual(InviteGroup.query.count(), 0)

    def test_admin_can_cancel_reservation_and_release_gift(self):
        with self.app.app_context():
            gift = db.session.get(Gift, 1)
            gift.status = "reserved"
            gift.reserved_by = "Convidado Exemplo"
            gift.reserved_at = datetime.now(timezone.utc)
            gift_id = gift.id
            db.session.commit()

        self.login_admin()
        dashboard = self.client.get("/admin/")
        self.assertIn("Cancelar reserva".encode(), dashboard.data)
        self.assertIn('class="confirm-dialog"'.encode(), dashboard.data)
        self.assertNotIn("onsubmit=\"return confirm('Cancelar a reserva".encode(), dashboard.data)
        response = self.client.post(f"/admin/presentes/{gift_id}/cancelar-reserva")
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            gift = db.session.get(Gift, gift_id)
            self.assertEqual(gift.status, "available")
            self.assertIsNone(gift.reserved_by)
            self.assertIsNone(gift.reserved_at)

        public_page = self.client.get("/")
        self.assertIn("Ver produto no marketplace".encode(), public_page.data)
        self.assertIn("Reservar este presente".encode(), public_page.data)

    def test_admin_marketplace_gift_requires_valid_product_link(self):
        self.login_admin()
        response = self.client.post("/admin/presentes/novo", data={
            "title": "Produto sem link",
            "description": "",
            "gift_type": "marketplace",
            "amount": "",
            "external_url": "",
            "emoji": "🎁",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Informe o link direto para o produto".encode(), response.data)

    def test_admin_cannot_add_second_honeymoon_gift(self):
        self.login_admin()
        response = self.client.post("/admin/presentes/novo", data={
            "title": "Outra cota",
            "description": "",
            "gift_type": "honeymoon",
            "amount": "",
            "external_url": "https://example.com/cota",
            "emoji": "🌴",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Já existe a cota para lua de mel".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(Gift.query.filter_by(gift_type="honeymoon").count(), 1)

    def test_admin_can_logout(self):
        self.login_admin()
        response = self.client.post("/admin/logout")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()
