"""tests/test_fitur.py -- Master Kode, Settings, Dashboard, Notifikasi, database."""

import io
import unittest

from tests.helpers import KasusAplikasi


class TestMasterKode(KasusAplikasi):
    def test_tambah_normalisasi_huruf_besar(self):
        h = self.masuk()
        r = self.client.post("/master-kode/", json={"kode": "  abc123 ", "keterangan": "uji"}, headers=h)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["kode"], "ABC123")

    def test_kode_kembar_409(self):
        h = self.masuk()
        r = self.client.post("/master-kode/", json={"kode": "AKL642"}, headers=h)
        self.assertEqual(r.status_code, 409)
        self.assertIn("sudah terdaftar", r.get_json()["error"])

    def test_format_kode_tidak_valid_400(self):
        h = self.masuk()
        for jelek in ("", "AB", "AKL-642", "AKL 642", "A" * 31, "KODE<script>"):
            with self.subTest(kode=jelek):
                r = self.client.post("/master-kode/", json={"kode": jelek}, headers=h)
                self.assertEqual(r.status_code, 400)

    def test_keterangan_terlalu_panjang(self):
        h = self.masuk()
        r = self.client.post("/master-kode/", json={"kode": "ABC123", "keterangan": "x" * 201}, headers=h)
        self.assertEqual(r.status_code, 400)

    def test_ubah_dan_kode_kembar(self):
        h = self.masuk()
        a = self.client.post("/master-kode/", json={"kode": "ABC123"}, headers=h).get_json()
        self.assertEqual(self.client.put(f"/master-kode/{a['id']}", json={"kode": "ABC999", "keterangan": "baru"}, headers=h).status_code, 200)
        self.assertEqual(self.client.put(f"/master-kode/{a['id']}", json={"kode": "AKL642"}, headers=h).status_code, 409)
        self.assertEqual(self.client.put("/master-kode/99999", json={"kode": "ZZZ999"}, headers=h).status_code, 404)

    def test_hapus_dan_404(self):
        h = self.masuk()
        a = self.client.post("/master-kode/", json={"kode": "ABC123"}, headers=h).get_json()
        self.assertEqual(self.client.delete(f"/master-kode/{a['id']}", headers=h).status_code, 200)
        self.assertEqual(self.client.delete(f"/master-kode/{a['id']}", headers=h).status_code, 404)

    def test_daftar_kode_valid_langsung_diperbarui(self):
        """Cache daftar kode harus dibatalkan saat Master Kode berubah (validasi OCR langsung memakai data terbaru)."""
        h = self.masuk()
        with self.app.app_context():
            from services import database
            self.assertNotIn("ZZZ999", database.get_daftar_kode_valid())
        a = self.client.post("/master-kode/", json={"kode": "ZZZ999"}, headers=h).get_json()
        with self.app.app_context():
            self.assertIn("ZZZ999", database.get_daftar_kode_valid())
        self.client.delete(f"/master-kode/{a['id']}", headers=h)
        with self.app.app_context():
            self.assertNotIn("ZZZ999", database.get_daftar_kode_valid())

    def test_kode_baru_langsung_bisa_dipindai(self):
        h = self.masuk()
        self.ocr.teks = "ZZZ999"
        self.assertEqual(self.kirim_foto(h).get_json()["status"], "NOT_FOUND")     # belum terdaftar: ditolak
        self.client.post("/master-kode/", json={"kode": "ZZZ999"}, headers=h)
        self.assertEqual(self.kirim_foto(h).get_json()["status"], "VALID")

    def test_halaman_meng_escape_keterangan_berbahaya(self):
        h = self.masuk()
        self.client.post("/master-kode/", json={"kode": "XSS123", "keterangan": "<script>alert(1)</script>"}, headers=h)
        isi = self.client.get("/master-kode/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", isi)
        self.assertIn("&lt;script&gt;", isi)

    def _xlsx(self, baris, kolom=("kode", "keterangan")):
        import pandas as pd
        buf = io.BytesIO()
        pd.DataFrame(baris, columns=list(kolom)).to_excel(buf, index=False)
        buf.seek(0)
        return buf

    def test_impor_excel_melewati_kembar_dan_melaporkan_gagal(self):
        h = self.masuk()
        buf = self._xlsx([("NEW001", "baru"), ("AKL642", "kembar"), ("bad code!", "jelek"), ("new002", None)])
        r = self.client.post("/master-kode/import", data={"file": (buf, "kode.xlsx")}, headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual((j["berhasil"], j["dilewati"], j["gagal"]), (2, 1, 1))
        with self.app.app_context():
            from services import database
            kode = database.get_daftar_kode_valid()
            self.assertIn("NEW001", kode)
            self.assertIn("NEW002", kode)       # huruf kecil dinormalkan

    def test_impor_membuat_notifikasi(self):
        h = self.masuk()
        self.client.post("/master-kode/import", data={"file": (self._xlsx([("NEW001", "a")]), "k.xlsx")}, headers=h,
                         content_type="multipart/form-data")
        daftar = self.client.get("/notifications/").get_json()["notifikasi"]
        self.assertEqual(daftar[0]["tipe"], "import_selesai")

    def test_impor_tidak_menimpa_keterangan_lama(self):
        h = self.masuk()
        self.client.post("/master-kode/import", data={"file": (self._xlsx([("AKL642", "DITIMPA?")]), "k.xlsx")}, headers=h,
                         content_type="multipart/form-data")
        with self.app.app_context():
            from services import database
            ket = [k["keterangan"] for k in database.get_all_master_kode() if k["kode"] == "AKL642"][0]
            self.assertEqual(ket, "uji")

    def test_impor_kolom_kode_tidak_ada_400(self):
        h = self.masuk()
        buf = self._xlsx([("a", "b")], kolom=("nama", "ket"))
        r = self.client.post("/master-kode/import", data={"file": (buf, "k.xlsx")}, headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("kode", r.get_json()["error"])

    def test_impor_format_salah_dan_tanpa_berkas(self):
        h = self.masuk()
        r = self.client.post("/master-kode/import", data={"file": (io.BytesIO(b"x"), "k.txt")}, headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/master-kode/import", headers=h).status_code, 400)

    def test_impor_berkas_rusak_400_bukan_500(self):
        h = self.masuk()
        r = self.client.post("/master-kode/import", data={"file": (io.BytesIO(b"bukan excel"), "k.xlsx")}, headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_hapus_kode_tidak_menghapus_riwayat(self):
        """FK ON DELETE SET NULL: riwayat lama tetap ada, hanya kodenya menjadi NULL."""
        h = self.masuk()
        self.ocr.teks = "AKL642"
        self.kirim_foto(h)
        with self.app.app_context():
            from services import database
            kid = [k["id"] for k in database.get_all_master_kode() if k["kode"] == "AKL642"][0]
        self.client.delete(f"/master-kode/{kid}", headers=h)
        riwayat = self.client.get("/history/search").get_json()
        self.assertEqual(len(riwayat), 1)
        self.assertIsNone(riwayat[0]["kode"])


class TestPengaturan(KasusAplikasi):
    def test_simpan_dan_baca_kembali(self):
        h = self.masuk()
        r = self.client.post("/settings/", json={"threshold_yolo": 0.55, "interval_scan": 800, "auto_scan": False, "kamera_aktif": "1"}, headers=h)
        self.assertEqual(r.status_code, 200)
        s = self.client.get("/settings/").get_data(as_text=True)
        self.assertIn('value="0.55"', s)
        self.assertIn('value="800"', s)
        j = r.get_json()
        self.assertEqual((j["threshold_yolo"], j["interval_scan"], j["auto_scan"], j["kamera_aktif"]), (0.55, 800, False, "1"))

    def test_bawaan_sesuai_pengujian(self):
        with self.app.app_context():
            from services import database
            s = database.get_settings()
            self.assertEqual((s.threshold_yolo, s.interval_scan, s.auto_scan), (0.4, 500, True))

    def test_validasi_rentang(self):
        h = self.masuk()
        for data in ({"threshold_yolo": 1.5}, {"threshold_yolo": -0.1}, {"threshold_yolo": "abc"},
                     {"interval_scan": 50}, {"interval_scan": 99999}, {"interval_scan": "x"}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post("/settings/", json=data, headers=h).status_code, 400)

    def test_pembaruan_sebagian_tidak_menimpa_lainnya(self):
        h = self.masuk()
        self.client.post("/settings/", json={"threshold_yolo": 0.7}, headers=h)
        j = self.client.post("/settings/", json={"interval_scan": 900}, headers=h).get_json()
        self.assertEqual((j["threshold_yolo"], j["interval_scan"]), (0.7, 900))

    def test_threshold_yolo_dipakai_alur_pindai(self):
        h = self.masuk()
        self.yolo.kotak = [(0.2, 0.3, 0.5, 0.85, 0.50)]
        self.assertEqual(self.kirim_foto(h).get_json()["status"], "VALID")          # 0.50 >= 0.4
        self.client.post("/settings/", json={"threshold_yolo": 0.8}, headers=h)
        r = self.kirim_foto(h).get_json()                                            # 0.50 < 0.8 -> tidak terdeteksi
        self.assertEqual(r["status"], "NOT_FOUND")
        self.assertIn("YOLO tidak mendeteksi", r["alasan_keputusan"])

    def test_halaman_settings_tidak_punya_pengaturan_ocr(self):
        self.masuk()
        self.assertNotIn("threshold-ocr", self.client.get("/settings/").get_data(as_text=True))


class TestDashboard(KasusAplikasi):
    def test_ringkasan_angka(self):
        h = self.masuk()
        self.kirim_foto(h)
        self.kirim_foto(h)
        with self.app.app_context():
            from services import database
            r = database.get_dashboard_summary()
        self.assertEqual(r["total_scan_hari_ini"], 2)
        self.assertEqual(r["total_barang"], len(self.KODE_AWAL))
        self.assertIsNotNone(r["confidence_rata_rata"])

    def test_tanpa_data_nilai_kosong_bukan_galat(self):
        self.masuk()
        isi = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Total scan hari ini", isi)

    def test_tanpa_peringatan_bila_sistem_siap(self):
        self.masuk()
        self.assertNotIn("banner-peringatan", self.client.get("/dashboard").get_data(as_text=True))

    def test_peringatan_master_kode_kosong(self):
        h = self.masuk()
        with self.app.app_context():
            from services import database
            for k in database.get_all_master_kode():
                database.delete_master_kode(k["id"])
        isi = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Master Kode masih kosong", isi)


class TestDashboardTanpaModel(KasusAplikasi):
    BUAT_MODEL = False

    def test_peringatan_model_belum_ada(self):
        self.masuk()
        self.assertIn("Model YOLO belum ada", self.client.get("/dashboard").get_data(as_text=True))

    def test_pindai_memberi_pesan_jelas_503(self):
        h = self.masuk()
        r = self.kirim_foto(h)
        self.assertEqual(r.status_code, 503)
        self.assertIn("models_ai", r.get_json()["error"])


class TestNotifikasi(KasusAplikasi):
    def _buat(self, tipe="scan_tidak_dikenali", pesan="uji"):
        with self.app.app_context():
            from services import notifications
            notifications.create(tipe, pesan)

    def test_daftar_dan_hitung_belum_dibaca(self):
        h = self.masuk()
        self._buat(pesan="satu")
        self._buat(pesan="dua")
        j = self.client.get("/notifications/").get_json()
        self.assertEqual(j["jumlah_belum_dibaca"], 2)
        self.assertEqual([n["pesan"] for n in j["notifikasi"]], ["dua", "satu"])      # terbaru dulu
        self.assertFalse(j["notifikasi"][0]["dibaca"])

    def test_tandai_dibaca_dan_404(self):
        h = self.masuk()
        self._buat()
        nid = self.client.get("/notifications/").get_json()["notifikasi"][0]["id"]
        self.assertEqual(self.client.post(f"/notifications/{nid}/read", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/notifications/").get_json()["jumlah_belum_dibaca"], 0)
        self.assertEqual(self.client.post("/notifications/99999/read", headers=h).status_code, 404)

    def test_tandai_semua(self):
        h = self.masuk()
        for _ in range(3):
            self._buat()
        self.assertEqual(self.client.post("/notifications/read-all", headers=h).get_json()["jumlah"], 3)
        self.assertEqual(self.client.get("/notifications/").get_json()["jumlah_belum_dibaca"], 0)

    def test_hanya_20_terbaru_ditampilkan(self):
        self.masuk()
        for i in range(25):
            self._buat(pesan=f"n{i}")
        j = self.client.get("/notifications/").get_json()
        self.assertEqual(len(j["notifikasi"]), 20)
        self.assertEqual(j["jumlah_belum_dibaca"], 25)

    def test_tipe_tidak_dikenal_ditolak(self):
        with self.app.app_context():
            from services import notifications
            with self.assertRaises(ValueError):
                notifications.create("ngawur", "x")

    def test_pesan_panjang_dipotong(self):
        self._buat(pesan="x" * 1000)
        self.masuk()
        self.assertLessEqual(len(self.client.get("/notifications/").get_json()["notifikasi"][0]["pesan"]), 300)


class TestDatabase(KasusAplikasi):
    def test_skema_aman_dijalankan_ulang(self):
        from database.db import init_db
        init_db(self.app)
        init_db(self.app)
        with self.app.app_context():
            from services import database
            self.assertEqual(len(database.get_all_master_kode()), len(self.KODE_AWAL))      # data tidak hilang

    def test_database_lama_tanpa_kolom_bacaan_dimigrasi_tanpa_kehilangan_data(self):
        """Database dari versi sebelumnya (tabel hasil_scan TANPA kolom teks_terbaca dan jarak_koreksi) harus dimigrasi."""
        import os, sqlite3, tempfile, shutil
        from app import create_app
        tmp = tempfile.mkdtemp()
        try:
            db_lama = os.path.join(tmp, "lama.db")
            conn = sqlite3.connect(db_lama)
            conn.executescript("""
                CREATE TABLE master_kode (id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, keterangan TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')), updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE hasil_scan (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, jam TEXT NOT NULL, kode TEXT,
                    confidence_yolo REAL NOT NULL, confidence_ocr REAL NOT NULL, processing_time REAL NOT NULL, status TEXT NOT NULL,
                    waktu_yolo REAL, waktu_ocr REAL, waktu_recovery REAL, alasan_keputusan TEXT, path_gambar TEXT, path_crop TEXT,
                    path_deteksi TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (kode) REFERENCES master_kode (kode) ON DELETE SET NULL ON UPDATE CASCADE);
                INSERT INTO master_kode (kode) VALUES ('AKL642');
                INSERT INTO hasil_scan (tanggal, jam, kode, confidence_yolo, confidence_ocr, processing_time, status)
                    VALUES ('2026-08-10', '10:00:00', 'AKL642', 0.9, 0.8, 4.9, 'VALID');
            """)
            conn.commit(); conn.close()
            kolom_sebelum = {r[1] for r in sqlite3.connect(db_lama).execute("PRAGMA table_info(hasil_scan)")}
            self.assertNotIn("teks_terbaca", kolom_sebelum)

            ov = {"DATABASE_PATH": db_lama, "UPLOAD_FOLDER": os.path.join(tmp, "u"), "EXPORT_FOLDER": os.path.join(tmp, "e"),
                  "LOG_FOLDER": os.path.join(tmp, "l"), "SECRET_KEY": "k", "ADMIN_PASSWORD": "rahasia123"}
            app = create_app("testing", overrides=ov)
            create_app("testing", overrides=ov)                      # dijalankan dua kali: harus aman
            kolom = {r[1] for r in sqlite3.connect(db_lama).execute("PRAGMA table_info(hasil_scan)")}
            self.assertTrue({"teks_terbaca", "jarak_koreksi"} <= kolom)
            with app.app_context():
                from services import database
                lama = database.get_scan_history()
                self.assertEqual(len(lama), 1, "data lama harus utuh")
                self.assertEqual((lama[0]["kode"], lama[0]["status"]), ("AKL642", "VALID"))
                self.assertIsNone(lama[0]["teks_terbaca"], "data lama memang tidak punya bacaan yang tercatat")
                baru = database.save_scan_result({"kode": None, "confidence_yolo": .9, "confidence_ocr": .5, "processing_time": 5.0,
                                                  "status": "NOT_FOUND", "teks_terbaca": "NAMMXD", "jarak_koreksi": 4.5})
                self.assertEqual((baru["teks_terbaca"], baru["jarak_koreksi"]), ("NAMMXD", 4.5))
            for h in list(app.logger.handlers):
                h.close(); app.logger.removeHandler(h)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_simpan_hasil_dengan_kode_di_luar_master_menjadi_null(self):
        with self.app.app_context():
            from services import database
            r = database.save_scan_result({"kode": "TIDAKADA9", "confidence_yolo": .9, "confidence_ocr": .9,
                                           "processing_time": 1.0, "status": "INVALID"})
            self.assertIsNone(r["kode"])
            self.assertEqual(r["status"], "INVALID")

    def test_pencarian_tidak_terjebak_karakter_khusus_like(self):
        h = self.masuk()
        self.ocr.teks = "AKL642"
        self.kirim_foto(h)
        self.assertEqual(len(self.client.get("/history/search?kode=%25").get_json()), 0)       # '%' bukan wildcard
        self.assertEqual(len(self.client.get("/history/search?kode=_").get_json()), 0)
        self.assertEqual(len(self.client.get("/history/search?kode=AKL").get_json()), 1)

    def test_injeksi_sql_lewat_filter_tidak_berpengaruh(self):
        self.masuk()
        r = self.client.get("/history/search?status=VALID' OR '1'='1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])


if __name__ == "__main__":
    unittest.main()
