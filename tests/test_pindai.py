"""tests/test_pindai.py -- unggah foto, alur pindai (mode cepat), riwayat, dan ekspor."""

import io
import os
import time
import unittest

from tests.helpers import KasusAplikasi


class TestPindaiFoto(KasusAplikasi):
    def test_tanpa_berkas_atau_format_salah_atau_bukan_gambar(self):
        h = self.masuk()
        self.assertEqual(self.client.post("/scan/image", headers=h).status_code, 400)
        r = self.client.post("/scan/image", data={"file": (io.BytesIO(b"x"), "a.txt")}, headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/scan/image", data={"file": (io.BytesIO(b"bukan gambar"), "a.jpg")}, headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("gambar", r.get_json()["error"])

    def test_valid_dengan_koreksi_o_menjadi_nol(self):
        h = self.masuk()
        self.ocr.teks = "AFTDWBO1"
        j = self.kirim_foto(h).get_json()
        self.assertEqual((j["status"], j["kode"]), ("VALID", "AFTDWB01"))
        self.assertIn("mode cepat", j["alasan_keputusan"])

    def test_bacaan_ngawur_ditolak_dan_kode_tidak_dicatat(self):
        h = self.masuk()
        self.ocr.teks = "NAMMXD"
        j = self.kirim_foto(h).get_json()
        self.assertEqual(j["status"], "NOT_FOUND")
        self.assertIsNone(j["kode"])
        self.assertIn("cek manual", j["alasan_keputusan"])

    def test_tepat_satu_panggilan_ocr_per_foto(self):
        h = self.masuk()
        self.kirim_foto(h)
        self.kirim_foto(h)
        self.assertEqual(len(self.ocr.panggilan), 2)

    def test_waktu_jalur_cadangan_selalu_nol(self):
        h = self.masuk()
        self.assertEqual(self.kirim_foto(h).get_json()["waktu_recovery"], 0.0)

    def test_crop_tegak_diputar_sebelum_dibaca(self):
        h = self.masuk()
        self.yolo.kotak = [(0.20, 0.10, 0.40, 0.90, 0.9)]       # kotak TEGAK
        self.kirim_foto(h)
        tinggi, lebar = self.ocr.panggilan[0]
        self.assertGreater(lebar, tinggi)

    def test_foto_besar_diperkecil_ke_1600_sebelum_yolo(self):
        h = self.masuk()
        self.kirim_foto(h, tinggi=2400, lebar=3200)
        self.assertEqual(max(self.yolo.dilihat[-1]), 1600)
        self.assertEqual(self.yolo.dilihat[-1], (1200, 1600))

    def test_foto_kecil_tidak_diubah_ukurannya(self):
        h = self.masuk()
        self.kirim_foto(h, tinggi=480, lebar=640)
        self.assertEqual(self.yolo.dilihat[-1], (480, 640))

    def test_tanpa_objek_terdeteksi_tidak_membuat_notifikasi(self):
        h = self.masuk()
        self.yolo.kotak = []
        j = self.kirim_foto(h).get_json()
        self.assertEqual(j["status"], "NOT_FOUND")
        self.assertIn("YOLO tidak mendeteksi", j["alasan_keputusan"])
        self.assertEqual(self.client.get("/notifications/").get_json()["jumlah_belum_dibaca"], 0)
        self.assertEqual(len(self.ocr.panggilan), 0, "tanpa objek, OCR tidak boleh dipanggil")

    def test_objek_terdeteksi_tapi_tidak_dikenali_membuat_notifikasi(self):
        h = self.masuk()
        self.ocr.teks = "NAMMXD"
        self.kirim_foto(h)
        n = self.client.get("/notifications/").get_json()["notifikasi"]
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0]["tipe"], "scan_tidak_dikenali")

    def test_scan_valid_tidak_membuat_notifikasi(self):
        h = self.masuk()
        self.kirim_foto(h)
        self.assertEqual(self.client.get("/notifications/").get_json()["jumlah_belum_dibaca"], 0)

    def test_hasil_tercatat_di_riwayat_dan_gambar_tersimpan(self):
        h = self.masuk()
        j = self.kirim_foto(h).get_json()
        riwayat = self.client.get("/history/search").get_json()
        self.assertEqual(len(riwayat), 1)
        self.assertEqual(riwayat[0]["kode"], j["kode"])
        for kunci in ("path_gambar", "path_crop", "path_deteksi"):
            self.assertRegex(riwayat[0][kunci], r"^static/uploads/[0-9a-f]{8}_(asli|crop|deteksi)\.jpg$")
            self.assertTrue(os.path.isfile(os.path.join(self.app.config["UPLOAD_FOLDER"], os.path.basename(riwayat[0][kunci]))))

    def test_dua_kotak_digabung_jadi_satu_crop(self):
        h = self.masuk()
        self.yolo.kotak = [(0.10, 0.10, 0.30, 0.50, 0.9), (0.50, 0.40, 0.70, 0.90, 0.6)]
        j = self.kirim_foto(h, tinggi=400, lebar=600).get_json()
        self.assertEqual(j["confidence_yolo"], 0.9)               # confidence tertinggi yang dilaporkan
        import cv2
        crop = cv2.imread(os.path.join(self.app.config["UPLOAD_FOLDER"], os.path.basename(j["path_crop"])))
        self.assertGreater(crop.shape[1], 0.5 * 600)              # lebar crop mencakup KEDUA kotak (>= 0.6 lebar foto)

    def test_kegagalan_di_dalam_alur_dijawab_500_tanpa_membocorkan_rincian(self):
        h = self.masuk()
        self.ocr.predict = lambda img: (_ for _ in ()).throw(RuntimeError("rahasia internal di /home/xyz"))
        r = self.kirim_foto(h)
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("rahasia internal", r.get_data(as_text=True))
        self.assertIn("logs/app.log", r.get_json()["error"])


class TestBacaanDiRiwayat(KasusAplikasi):
    """Bacaan OCR apa adanya (juga saat ditolak) tampil di hasil pindai, History, notifikasi, dan ekspor."""

    def test_hasil_pindai_membawa_bacaan_walau_ditolak(self):
        h = self.masuk()
        self.ocr.teks = "NAMMXD"
        j = self.kirim_foto(h).get_json()
        self.assertEqual((j["status"], j["kode"]), ("NOT_FOUND", None))
        self.assertEqual(j["teks_terbaca"], "NAMMXD")
        self.assertIn("NAMMXD", j["alasan_keputusan"])
        self.assertGreater(j["jarak_koreksi"], 2.0)

    def test_hasil_valid_menyimpan_bacaan_sebelum_koreksi(self):
        h = self.masuk()
        self.ocr.teks = "AFTDWBO1"
        j = self.kirim_foto(h).get_json()
        self.assertEqual((j["kode"], j["teks_terbaca"]), ("AFTDWB01", "AFTDWBO1"))

    def test_bacaan_tersimpan_dan_muncul_di_riwayat(self):
        h = self.masuk()
        for teks in ("NAMMXD", "AKL642"):
            self.ocr.teks = teks
            self.kirim_foto(h)
        riwayat = {r["teks_terbaca"]: r for r in self.client.get("/history/search").get_json()}
        self.assertEqual(set(riwayat), {"NAMMXD", "AKL642"})
        self.assertEqual(riwayat["NAMMXD"]["status"], "NOT_FOUND")
        self.assertIsNone(riwayat["NAMMXD"]["kode"])

    def test_tanpa_objek_tidak_ada_bacaan(self):
        h = self.masuk()
        self.yolo.kotak = []
        j = self.kirim_foto(h).get_json()
        self.assertIsNone(j["teks_terbaca"])
        self.assertIsNone(j["jarak_koreksi"])
        self.assertEqual(len(self.ocr.panggilan), 0, "tanpa objek OCR tidak dijalankan, jadi memang tidak ada bacaan")

    def test_ocr_tidak_menemukan_teks_disimpan_sebagai_kosong_bukan_null(self):
        h = self.masuk()
        self.ocr.teks = ""
        j = self.kirim_foto(h).get_json()
        self.assertEqual(j["teks_terbaca"], "")
        self.assertEqual(self.client.get("/history/search").get_json()[0]["teks_terbaca"], "")

    def test_notifikasi_menyebut_bacaan(self):
        h = self.masuk()
        self.ocr.teks = "NAMMXD"
        self.kirim_foto(h)
        pesan = self.client.get("/notifications/").get_json()["notifikasi"][0]["pesan"]
        self.assertIn("NAMMXD", pesan)

    def test_notifikasi_tanpa_teks(self):
        h = self.masuk()
        self.ocr.teks = ""
        self.kirim_foto(h)
        self.assertIn("tidak ada teks", self.client.get("/notifications/").get_json()["notifikasi"][0]["pesan"])

    def test_halaman_history_punya_kolom_bacaan_ocr(self):
        self.masuk()
        isi = self.client.get("/history/").get_data(as_text=True)
        self.assertIn("Bacaan OCR", isi)
        self.assertEqual(isi.count("<th>"), 9)

    def test_panel_monitoring_punya_baris_bacaan_ocr(self):
        self.masuk()
        self.assertIn('id="r-teks"', self.client.get("/monitoring/").get_data(as_text=True))

    def test_ekspor_excel_memuat_bacaan_ocr(self):
        import pandas as pd
        h = self.masuk()
        for teks in ("NAMMXD", "AKL642", ""):
            self.ocr.teks = teks
            self.kirim_foto(h)
        with self.app.app_context():                              # baris tanpa bacaan tercatat (mis. data lama): tampil sebagai "-"
            from services import database
            database.save_scan_result({"kode": None, "confidence_yolo": .9, "confidence_ocr": 0, "processing_time": 1, "status": "NOT_FOUND"})
        df = pd.read_excel(io.BytesIO(self.client.get("/export/excel").data))
        self.assertIn("Bacaan OCR", df.columns)
        self.assertEqual(sorted(df["Bacaan OCR"]), sorted(["NAMMXD", "AKL642", "(tidak ada teks)", "-"]))

    def test_ekspor_pdf_tetap_valid(self):
        h = self.masuk()
        self.ocr.teks = "NAMMXD"
        self.kirim_foto(h)
        self.assertTrue(self.client.get("/export/pdf").data.startswith(b"%PDF"))


class TestRiwayat(KasusAplikasi):
    def _isi(self, h):
        for teks in ("AKL642", "AFTDWB01", "NAMMXD"):
            self.ocr.teks = teks
            self.kirim_foto(h)

    def test_pencarian_menurut_status_dan_kode(self):
        h = self.masuk()
        self._isi(h)
        self.assertEqual(len(self.client.get("/history/search").get_json()), 3)
        self.assertEqual(len(self.client.get("/history/search?status=VALID").get_json()), 2)
        self.assertEqual(len(self.client.get("/history/search?status=NOT_FOUND").get_json()), 1)
        self.assertEqual(len(self.client.get("/history/search?kode=AKL").get_json()), 1)
        self.assertEqual(len(self.client.get("/history/search?kode=akl").get_json()), 1)        # LIKE tidak membedakan huruf

    def test_pencarian_menurut_tanggal(self):
        h = self.masuk()
        self._isi(h)
        from datetime import date
        self.assertEqual(len(self.client.get(f"/history/search?tanggal={date.today().isoformat()}").get_json()), 3)
        self.assertEqual(len(self.client.get("/history/search?tanggal=2000-01-01").get_json()), 0)

    def test_urutan_terbaru_dulu(self):
        h = self.masuk()
        self._isi(h)
        ids = [r["id"] for r in self.client.get("/history/search").get_json()]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_hapus_menghapus_baris_dan_gambarnya(self):
        h = self.masuk()
        self.kirim_foto(h)
        r = self.client.get("/history/search").get_json()[0]
        berkas = [os.path.join(self.app.config["UPLOAD_FOLDER"], os.path.basename(r[k])) for k in ("path_gambar", "path_crop", "path_deteksi")]
        self.assertTrue(all(os.path.isfile(b) for b in berkas))
        self.assertEqual(self.client.delete(f"/history/{r['id']}", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/history/search").get_json(), [])
        self.assertFalse(any(os.path.isfile(b) for b in berkas), "gambar milik riwayat harus ikut terhapus")
        self.assertEqual(self.client.delete(f"/history/{r['id']}", headers=h).status_code, 404)

    def test_hapus_tidak_pernah_menyentuh_berkas_di_luar_folder_unggahan(self):
        """Walau path di database dimanipulasi menuju berkas lain, berkas itu tidak boleh terhapus."""
        h = self.masuk()
        korban = os.path.join(self.tmp, "penting.txt")
        open(korban, "w").write("jangan dihapus")
        with self.app.app_context():
            from database.db import get_connection
            from services import database
            database.save_scan_result({"kode": None, "confidence_yolo": 1, "confidence_ocr": 1, "processing_time": 1, "status": "NOT_FOUND",
                                       "path_gambar": "../penting.txt", "path_crop": korban, "path_deteksi": "static/uploads/../../penting.txt"})
            rid = get_connection().execute("SELECT id FROM hasil_scan").fetchone()["id"]
        self.assertEqual(self.client.delete(f"/history/{rid}", headers=h).status_code, 200)
        self.assertTrue(os.path.isfile(korban), "berkas di luar folder unggahan TIDAK boleh terhapus")

    def test_halaman_history_terbuka(self):
        self.masuk()
        isi = self.client.get("/history/").get_data(as_text=True)
        self.assertIn("pagination-controls", isi)
        self.assertIn("history.js", isi)


class TestEkspor(KasusAplikasi):
    def _isi(self, h):
        for teks in ("AKL642", "AFTDWB01", "NAMMXD"):
            self.ocr.teks = teks
            self.kirim_foto(h)

    def test_pdf_valid(self):
        h = self.masuk()
        self._isi(h)
        r = self.client.get("/export/pdf")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertIn("attachment", r.headers["Content-Disposition"])

    def test_excel_valid_dan_berisi_data(self):
        import pandas as pd
        h = self.masuk()
        self._isi(h)
        r = self.client.get("/export/excel")
        self.assertEqual(r.status_code, 200)
        df = pd.read_excel(io.BytesIO(r.data))
        self.assertEqual(len(df), 3)
        self.assertIn("Kode", df.columns)
        self.assertNotIn("Waktu Recovery (s)", df.columns)

    def test_ekspor_menghormati_filter(self):
        import pandas as pd
        h = self.masuk()
        self._isi(h)
        df = pd.read_excel(io.BytesIO(self.client.get("/export/excel?status=VALID").data))
        self.assertEqual(len(df), 2)
        self.assertEqual(set(df["Status"]), {"VALID"})
        df = pd.read_excel(io.BytesIO(self.client.get("/export/excel?kode=AKL").data))
        self.assertEqual(list(df["Kode"]), ["AKL642"])

    def test_ekspor_tanpa_data_tetap_berhasil(self):
        self.masuk()
        self.assertTrue(self.client.get("/export/pdf").data.startswith(b"%PDF"))
        import pandas as pd
        self.assertEqual(len(pd.read_excel(io.BytesIO(self.client.get("/export/excel").data))), 0)

    def test_berkas_ekspor_lama_dibersihkan(self):
        self.masuk()
        folder = self.app.config["EXPORT_FOLDER"]
        os.makedirs(folder, exist_ok=True)
        lama = os.path.join(folder, "laporan_scan_lama0001.pdf")
        lain = os.path.join(folder, "catatan_penting.txt")
        for p in (lama, lain):
            open(p, "w").write("x")
        dua_hari = time.time() - 48 * 3600
        os.utime(lama, (dua_hari, dua_hari))
        os.utime(lain, (dua_hari, dua_hari))
        self.client.get("/export/pdf")
        self.assertFalse(os.path.exists(lama), "berkas ekspor lebih dari 24 jam harus dibersihkan")
        self.assertTrue(os.path.exists(lain), "berkas lain tidak boleh disentuh")


if __name__ == "__main__":
    unittest.main()
