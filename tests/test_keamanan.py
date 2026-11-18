"""tests/test_keamanan.py -- login, kunci akun, CSRF, wajib login, ganti akun, akun awal, header keamanan."""

import os
import unittest
from datetime import datetime, timedelta

from tests.helpers import KasusAplikasi, PASSWORD_UJI


class TestWajibLogin(KasusAplikasi):
    def test_halaman_tanpa_login_dialihkan_ke_login_dengan_next(self):
        r = self.client.get("/history/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?next=/history/", r.headers["Location"])

    def test_api_tanpa_login_dijawab_401_json(self):
        for url in ("/history/search", "/camera/status", "/scan/status", "/notifications/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 401, url)
            self.assertIn("error", r.get_json())

    def test_permintaan_ubah_data_tanpa_login_ditolak(self):
        r = self.client.post("/master-kode/", json={"kode": "ABC123"})
        self.assertEqual(r.status_code, 401)
        with self.app.app_context():
            from services import database
            self.assertNotIn("ABC123", database.get_daftar_kode_valid())

    def test_halaman_login_terbuka_tanpa_login(self):
        self.assertEqual(self.client.get("/login").status_code, 200)

    def test_berkas_static_terbuka_tanpa_login(self):
        self.assertEqual(self.client.get("/static/css/style.css").status_code, 200)

    def test_url_tidak_dikenal_memberi_404_bukan_alihan(self):
        self.assertEqual(self.client.get("/tidak-ada-halaman").status_code, 404)


class TestLogin(KasusAplikasi):
    def test_login_benar_masuk_ke_dashboard(self):
        r = self.login()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/dashboard"))
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_password_salah_401_dan_pesan_umum(self):
        r = self.login(password="salah")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Username atau password salah", r.get_data(as_text=True))

    def test_username_tidak_ada_pesannya_sama_dengan_password_salah(self):
        a = self.login(username="tidak_ada", password="apa saja").get_data(as_text=True)
        b = self.login(password="salah").get_data(as_text=True)
        self.assertIn("Username atau password salah", a)
        self.assertIn("Username atau password salah", b)

    def test_next_ke_situs_lain_diabaikan(self):
        for jahat in ("http://evil.example/x", "//evil.example/x", "https://evil.example", "/\\evil.example"):
            with self.subTest(next=jahat):
                c = self.app.test_client()
                c.get("/login")
                with c.session_transaction() as s:
                    token = s["csrf_token"]
                r = c.post("/login?next=" + jahat, data={"username": "admin", "password": PASSWORD_UJI, "csrf_token": token})
                self.assertEqual(r.status_code, 302)
                self.assertNotIn("evil", r.headers["Location"])

    def test_next_di_situs_sendiri_dihormati(self):
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf_token"]
        r = c.post("/login?next=/history/", data={"username": "admin", "password": PASSWORD_UJI, "csrf_token": token})
        self.assertTrue(r.headers["Location"].endswith("/history/"))

    def test_login_tanpa_token_csrf_ditolak(self):
        c = self.app.test_client()
        c.get("/login")
        r = c.post("/login", data={"username": "admin", "password": PASSWORD_UJI})
        self.assertEqual(r.status_code, 403)

    def test_logout_menghapus_sesi(self):
        h = self.masuk()
        self.assertEqual(self.client.post("/logout", headers=h).status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_logout_wajib_post(self):
        self.masuk()
        self.assertEqual(self.client.get("/logout").status_code, 405)

    def test_sesi_baru_setelah_login(self):
        """Sesi dibersihkan saat login (mencegah session fixation): data lama tidak ikut terbawa."""
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            s["data_lama"] = "sisa"
            token = s["csrf_token"]
        c.post("/login", data={"username": "admin", "password": PASSWORD_UJI, "csrf_token": token})
        with c.session_transaction() as s:
            self.assertNotIn("data_lama", s)
            self.assertIn("user_id", s)


class TestKunciAkun(KasusAplikasi):
    def _gagal(self, n, username="admin"):
        for _ in range(n):
            self.login(username=username, password="salah")

    def test_terkunci_setelah_lima_kali_gagal_walau_password_benar(self):
        self._gagal(5)
        r = self.login()                       # password BENAR, tetapi sudah terkunci
        self.assertEqual(r.status_code, 429)
        self.assertIn("Terlalu banyak percobaan", r.get_data(as_text=True))
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_empat_kali_gagal_belum_terkunci(self):
        self._gagal(4)
        self.assertEqual(self.login().status_code, 302)

    def test_login_berhasil_mereset_hitungan(self):
        self._gagal(4)
        self.assertEqual(self.login().status_code, 302)
        self.client.post("/logout", headers={"X-CSRF-Token": self._token()})
        self._gagal(4)                         # hitungan mulai dari nol lagi
        self.assertEqual(self.login().status_code, 302)

    def _token(self):
        with self.client.session_transaction() as s:
            return s.get("csrf_token", "")

    def test_kunci_tidak_bisa_dilewati_dengan_huruf_besar(self):
        self._gagal(5)
        self.assertEqual(self.login(username="ADMIN").status_code, 429)

    def test_kunci_per_username_tidak_mengunci_orang_lain(self):
        with self.app.app_context():
            from services import auth
            auth.buat_pengguna("operator", "sandi-operator")
        self._gagal(5, username="admin")
        self.assertEqual(self.login(username="operator", password="sandi-operator").status_code, 302)

    def test_kunci_berakhir_setelah_durasi(self):
        self._gagal(5)
        from services import auth
        with auth._lock:
            auth._percobaan["admin"]["terkunci_hingga"] = datetime.now() - timedelta(seconds=1)
        self.assertEqual(self.login().status_code, 302)


class TestCsrf(KasusAplikasi):
    def test_post_tanpa_token_ditolak_403(self):
        self.masuk()
        r = self.client.post("/master-kode/", json={"kode": "ABC123"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("CSRF", r.get_json()["error"])

    def test_token_salah_ditolak(self):
        self.masuk()
        r = self.client.post("/master-kode/", json={"kode": "ABC123"}, headers={"X-CSRF-Token": "palsu"})
        self.assertEqual(r.status_code, 403)

    def test_token_benar_diterima(self):
        h = self.masuk()
        self.assertEqual(self.client.post("/master-kode/", json={"kode": "ABC123"}, headers=h).status_code, 201)

    def test_put_delete_juga_dilindungi(self):
        h = self.masuk()
        kode_id = self.client.post("/master-kode/", json={"kode": "ABC123"}, headers=h).get_json()["id"]
        self.assertEqual(self.client.put(f"/master-kode/{kode_id}", json={"kode": "ABC124"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/master-kode/{kode_id}").status_code, 403)
        self.assertEqual(self.client.delete(f"/master-kode/{kode_id}", headers=h).status_code, 200)

    def test_token_lewat_field_formulir(self):
        h = self.masuk()
        r = self.client.post("/settings/", data={"interval_scan": "700", "csrf_token": h["X-CSRF-Token"]})
        self.assertEqual(r.status_code, 200)

    def test_token_sesi_lain_tidak_berlaku(self):
        h = self.masuk()
        c2 = self.app.test_client()
        self.login(client=c2)
        self.assertEqual(c2.post("/master-kode/", json={"kode": "ABC123"}, headers=h).status_code, 403)

    def test_get_tidak_memerlukan_token(self):
        self.masuk()
        self.assertEqual(self.client.get("/history/search").status_code, 200)

    def test_halaman_memuat_meta_token(self):
        self.masuk()
        isi = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('name="csrf-token"', isi)


class TestGantiAkun(KasusAplikasi):
    def _ubah(self, h, **data):
        return self.client.post("/account", data=data, headers=h)

    def test_password_saat_ini_salah_ditolak(self):
        h = self.masuk()
        r = self._ubah(h, password_sekarang="salah", password_baru="baru-123", konfirmasi_password="baru-123")
        self.assertEqual(r.status_code, 400)

    def test_konfirmasi_tidak_cocok(self):
        h = self.masuk()
        r = self._ubah(h, password_sekarang=PASSWORD_UJI, password_baru="baru-123", konfirmasi_password="beda-123")
        self.assertEqual(r.status_code, 400)

    def test_password_terlalu_pendek(self):
        h = self.masuk()
        r = self._ubah(h, password_sekarang=PASSWORD_UJI, password_baru="abc", konfirmasi_password="abc")
        self.assertEqual(r.status_code, 400)

    def test_ganti_password_berhasil_dan_bisa_login_dengan_yang_baru(self):
        h = self.masuk()
        self.assertEqual(self._ubah(h, password_sekarang=PASSWORD_UJI, password_baru="baru-123", konfirmasi_password="baru-123").status_code, 200)
        c2 = self.app.test_client()
        self.assertEqual(self.login(client=c2, password=PASSWORD_UJI).status_code, 401)
        self.assertEqual(self.login(client=c2, password="baru-123").status_code, 302)

    def test_ganti_username_dan_username_kembar(self):
        with self.app.app_context():
            from services import auth
            auth.buat_pengguna("operator", "sandi-operator")
        h = self.masuk()
        self.assertEqual(self._ubah(h, password_sekarang=PASSWORD_UJI, username_baru="operator").status_code, 409)
        r = self._ubah(h, password_sekarang=PASSWORD_UJI, username_baru="supervisor")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["username"], "supervisor")
        self.assertEqual(self.login(client=self.app.test_client(), username="supervisor").status_code, 302)

    def test_password_tersimpan_sebagai_hash(self):
        with self.app.app_context():
            from database.db import get_connection
            row = get_connection().execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()
            self.assertNotEqual(row["password_hash"], PASSWORD_UJI)
            self.assertNotIn(PASSWORD_UJI, row["password_hash"])


class TestHeaderDanGalat(KasusAplikasi):
    def test_header_keamanan(self):
        r = self.client.get("/login")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(r.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_cookie_sesi_httponly(self):
        r = self.client.get("/login")
        self.assertIn("HttpOnly", r.headers.get("Set-Cookie", ""))

    def test_404_html_untuk_browser(self):
        r = self.client.get("/tidak-ada", headers={"Accept": "text/html"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("Halaman tidak ditemukan", r.get_data(as_text=True))

    def test_405_json_untuk_api(self):
        self.masuk()
        r = self.client.get("/scan/live")
        self.assertEqual(r.status_code, 405)
        self.assertIn("error", r.get_json())

    def test_unggahan_terlalu_besar_413(self):
        h = self.masuk()
        self.app.config["MAX_CONTENT_LENGTH"] = 1000
        import io
        r = self.client.post("/scan/image", data={"file": (io.BytesIO(b"x" * 5000), "a.jpg")}, headers=h,
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 413)


class TestSesiSetelahRestart(KasusAplikasi):
    """
    Setelah aplikasi dijalankan ulang, sesi login lama TIDAK berlaku lagi dan pengguna diminta masuk lagi.
    Restart disimulasikan dengan mengganti ID_SERVER (penanda umur proses) di utils.security.
    """

    def setUp(self):
        super().setUp()
        from utils import security
        self._id_asli = security.ID_SERVER
        self._env_asli = os.environ.get("SESI_BERAKHIR_SAAT_RESTART")

    def tearDown(self):
        from utils import security
        security.ID_SERVER = self._id_asli
        if self._env_asli is None:
            os.environ.pop("SESI_BERAKHIR_SAAT_RESTART", None)
        else:
            os.environ["SESI_BERAKHIR_SAAT_RESTART"] = self._env_asli
        super().tearDown()

    def _restart(self):
        import secrets
        from utils import security
        security.ID_SERVER = secrets.token_hex(16)

    def test_sebelum_restart_sesi_tetap_berlaku_di_banyak_permintaan(self):
        self.masuk()
        for url in ("/dashboard", "/history/", "/settings/", "/dashboard"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_halaman_setelah_restart_dialihkan_ke_login_dengan_pesan(self):
        self.masuk()
        self._restart()
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertIn("sesi=berakhir", r.headers["Location"])

    def test_api_setelah_restart_dijawab_401(self):
        self.masuk()
        self._restart()
        for url in ("/history/search", "/notifications/", "/camera/status"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 401, url)
            self.assertIn("error", r.get_json())

    def test_halaman_login_tidak_berputar_dan_menampilkan_pesan(self):
        """Risiko: sesi lama membuat /login mengalihkan ke dashboard, dashboard mengalihkan ke /login, dan seterusnya."""
        self.masuk()
        self._restart()
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200, "/login harus menampilkan formulir, bukan mengalihkan")
        r = self.client.get("/login?sesi=berakhir")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Silakan masuk lagi", r.get_data(as_text=True))

    def test_tanpa_parameter_tidak_ada_pesan(self):
        self.assertNotIn("Silakan masuk lagi", self.client.get("/login").get_data(as_text=True))

    def test_pesan_hanya_teks_tetap_tidak_bisa_disuntik(self):
        r = self.client.get("/login?sesi=<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)", r.get_data(as_text=True))

    def test_sesi_lama_dibersihkan(self):
        self.masuk()
        self._restart()
        self.client.get("/dashboard")
        with self.client.session_transaction() as s:
            self.assertNotIn("user_id", s)

    def test_permintaan_ubah_data_dengan_sesi_lama_ditolak_dan_tidak_dijalankan(self):
        h = self.masuk()                       # h berisi token CSRF yang SAH untuk sesi lama
        self._restart()
        r = self.client.post("/master-kode/", json={"kode": "BARU999"}, headers=h)
        self.assertEqual(r.status_code, 401)
        with self.app.app_context():
            from services import database
            self.assertNotIn("BARU999", database.get_daftar_kode_valid())

    def test_login_ulang_setelah_restart_berhasil(self):
        self.masuk()
        self._restart()
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_restart_kedua_juga_mengakhiri_sesi_baru(self):
        self.masuk()
        self._restart()
        self.login()
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self._restart()
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_pengguna_lain_tidak_terpengaruh_pengguna_yang_baru_login(self):
        self.masuk()
        c2 = self.app.test_client()
        self.login(client=c2)
        self._restart()
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(c2.get("/dashboard").status_code, 302)       # keduanya sama-sama berakhir
        self.login(client=c2)
        self.assertEqual(c2.get("/dashboard").status_code, 200)

    def test_dapat_dimatikan_lewat_pengaturan(self):
        os.environ["SESI_BERAKHIR_SAAT_RESTART"] = "0"
        self.masuk()
        self._restart()
        self.assertEqual(self.client.get("/dashboard").status_code, 200, "dengan pengaturan dimatikan, sesi lama tetap berlaku")

    def test_logout_biasa_tetap_bekerja(self):
        h = self.masuk()
        self.client.post("/logout", headers=h)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)


class TestAkunAwal(unittest.TestCase):
    def _buat(self, tmp, **tambahan):
        from app import create_app
        ov = {"DATABASE_PATH": os.path.join(tmp, "x.db"), "UPLOAD_FOLDER": os.path.join(tmp, "u"),
              "EXPORT_FOLDER": os.path.join(tmp, "e"), "LOG_FOLDER": os.path.join(tmp, "l"), "SECRET_KEY": "k"}
        ov.update(tambahan)
        return create_app("testing", overrides=ov)

    def test_password_acak_dibuat_dan_disimpan_bila_tidak_diatur(self):
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        try:
            app = self._buat(tmp, ADMIN_PASSWORD=None)
            berkas = os.path.join(tmp, "kredensial_awal.txt")
            self.assertTrue(os.path.isfile(berkas))
            isi = open(berkas, encoding="utf-8").read()
            password = [b for b in isi.splitlines() if b.startswith("Password:")][0].split(": ")[1]
            self.assertGreaterEqual(len(password), 12)
            c = app.test_client()
            c.get("/login")
            with c.session_transaction() as s:
                token = s["csrf_token"]
            r = c.post("/login", data={"username": "admin", "password": password, "csrf_token": token})
            self.assertEqual(r.status_code, 302)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tidak_membuat_akun_kedua_saat_dijalankan_ulang(self):
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        try:
            self._buat(tmp, ADMIN_PASSWORD="rahasia123")
            app = self._buat(tmp, ADMIN_PASSWORD="rahasia123")
            with app.app_context():
                from services import auth
                self.assertEqual(auth.jumlah_pengguna(), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
