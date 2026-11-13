from io import BytesIO
import unittest

from PIL import Image, ImageChops
import qrcode

from app import create_app
from app.extensions import db
from app.models import InviteGroup


class InviteQRCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-only-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "PUBLIC_SITE_URL": "https://convites.example",
        })

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def setUp(self):
        self.client = self.app.test_client()
        self.app.config["PUBLIC_SITE_URL"] = "https://convites.example"
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            group = InviteGroup(reference_name="Familia Teste", guest_names="Pessoa Teste", invite_token="private-test-token-12345")
            db.session.add(group)
            db.session.commit()
            self.group_id = group.id
            self.token = group.invite_token
        self.image_url = f"/admin/convites/{self.group_id}/qrcode.png"
        self.print_url = f"/admin/convites/{self.group_id}/imprimir"

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()

    def authenticate(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True

    def test_qr_and_print_require_admin(self):
        for path in (self.image_url, self.image_url + "?download=1", self.print_url):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.location)

    def test_png_encodes_public_url_instead_of_request_host(self):
        self.authenticate()
        response = self.client.get(self.image_url, base_url="http://localhost:5000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
        expected = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=16, border=4)
        expected.add_data(f"https://convites.example/confirmar-presenca/{self.token}")
        expected.make(fit=True)
        expected_image = expected.make_image(fill_color="black", back_color="white").convert("RGB")
        with Image.open(BytesIO(response.data)) as image:
            self.assertGreaterEqual(image.width, 600)
            self.assertEqual(image.width, image.height)
            self.assertEqual(image.size, expected_image.size)
            self.assertIsNone(ImageChops.difference(image.convert("RGB"), expected_image).getbbox())
            self.assertEqual(image.convert("RGB").getpixel((0, 0)), (255, 255, 255))

    def test_download_has_safe_filename_without_private_token(self):
        self.authenticate()
        response = self.client.get(self.image_url + "?download=1")
        self.assertEqual(response.status_code, 200)
        disposition = response.headers["Content-Disposition"]
        self.assertIn("attachment;", disposition)
        self.assertIn("familia-teste-qrcode.png", disposition)
        self.assertNotIn(self.token, disposition)
        self.assertNotIn("Familia", disposition)

    def test_print_page_and_dashboard_offer_qr_actions(self):
        self.authenticate()
        response = self.client.get(self.print_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.image_url, response.get_data(as_text=True))
        self.assertIn("window.print()", response.get_data(as_text=True))
        self.assertIn(f"https://convites.example/confirmar-presenca/{self.token}", response.get_data(as_text=True))
        dashboard = self.client.get("/admin/").get_data(as_text=True)
        self.assertIn("Baixar QR Code", dashboard)
        self.assertIn(self.print_url, dashboard)
        self.assertIn("Link alternativo", dashboard)
        with self.app.app_context():
            self.assertEqual(db.session.get(InviteGroup, self.group_id).invite_token, self.token)

    def test_rotating_link_changes_qr_and_invalidates_previous_token(self):
        self.authenticate()
        before = self.client.get(self.image_url).data
        response = self.client.post(f"/admin/convites/{self.group_id}/renovar-link")
        self.assertEqual(response.status_code, 302)
        after = self.client.get(self.image_url).data
        self.assertNotEqual(before, after)
        with self.app.app_context():
            self.assertIsNone(InviteGroup.query.filter_by(invite_token=self.token).first())
            self.assertIsNotNone(db.session.get(InviteGroup, self.group_id).invite_token)

    def test_missing_invite_returns_404(self):
        self.authenticate()
        for suffix in ("qrcode.png", "imprimir"):
            self.assertEqual(self.client.get(f"/admin/convites/999/{suffix}").status_code, 404)

    def test_group_without_token_does_not_generate_an_open_qr(self):
        self.authenticate()
        with self.app.app_context():
            db.session.get(InviteGroup, self.group_id).invite_token = None
            db.session.commit()
        self.assertEqual(self.client.get(self.image_url).status_code, 404)
        self.assertEqual(self.client.get(self.print_url).status_code, 404)

    def test_invalid_public_url_is_not_encoded(self):
        self.authenticate()
        for base_url in ("http://localhost:5000", "https://site.example/path", "https://user:pass@site.example", "https://site.example?other=1"):
            with self.subTest(base_url=base_url):
                self.app.config["PUBLIC_SITE_URL"] = base_url
                self.assertEqual(self.client.get(self.image_url).status_code, 503)
