"""
tests/test_core.py -- uji inti pembaca kode (core/): validasi, pembaca mode cepat, detektor.
Jalankan:  python -m unittest discover -s tests -v
"""

import unittest

import numpy as np

from tests.helpers import OcrTiruan  # noqa: F401  (juga memasang sys.path)
from core import detector, ocr, reader, validation

import cv2


def _teks_terang(tinggi=140, lebar=520, tulisan="AKL636EEA 642"):
    """Gambar mendatar: teks TERANG di latar GELAP (jenis gambar yang diperlakukan deskew sebagai 'teks')."""
    img = np.full((tinggi, lebar, 3), 30, np.uint8)
    cv2.putText(img, tulisan, (20, int(tinggi * 0.72)), cv2.FONT_HERSHEY_SIMPLEX, 1.9, (235, 235, 235), 6)
    return img


def _putar(img, derajat, isi):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), derajat, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    W, H = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += W / 2 - w // 2
    M[1, 2] += H / 2 - h // 2
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=isi)


def _sisa_miring(img):
    """Penaksir kemiringan INDEPENDEN dari deskew: sudut (-20..20) yang memaksimalkan variansi proyeksi baris."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    biner = cv2.cvtColor(((g > 130).astype(np.uint8) * 255), cv2.COLOR_GRAY2BGR)
    terbaik, nilai = 0.0, -1.0
    for a in np.arange(-30, 30.01, 1.0):
        v = float(np.var(_putar(biner, a, (0, 0, 0))[:, :, 0].sum(axis=1)))
        if v > nilai:
            nilai, terbaik = v, float(a)
    return terbaik


KODE = ["AFTDWB01", "AKL608IEE", "AKL609EEA", "AKL636EE", "AKL636EEA", "AKL636EED", "AKL642"]


class TestValidasi(unittest.TestCase):
    def test_bacaan_persis_diterima_dengan_jarak_nol(self):
        self.assertEqual(validation.koreksi_ke_kode_valid("AKL642", KODE), ("AKL642", 0.0, True))

    def test_o_dan_nol_dikoreksi(self):
        kode, jarak, yakin = validation.koreksi_ke_kode_valid("AFTDWBO1", KODE)
        self.assertEqual((kode, yakin), ("AFTDWB01", True))
        self.assertAlmostEqual(jarak, 1.0)

    def test_pasangan_mirip_berbiaya_murah(self):
        kode, jarak, yakin = validation.koreksi_ke_kode_valid("AKL636EF", KODE)   # E <-> F
        self.assertTrue(yakin)
        self.assertEqual(kode, "AKL636EE")
        self.assertAlmostEqual(jarak, 0.3)

    def test_bacaan_jauh_ditolak(self):
        _, jarak, yakin = validation.koreksi_ke_kode_valid("MMOAR", KODE)
        self.assertFalse(yakin)
        self.assertGreater(jarak, validation.AMBANG_TERIMA_JARAK)

    def test_ambang_bawaan_2_dan_dapat_diubah(self):
        self.assertEqual(validation.AMBANG_TERIMA_JARAK, 2.0)
        # 'AFTDVBO1' berjarak 2.0 dari AFTDWB01: diterima pada 2.0, ditolak pada 1.0
        self.assertTrue(validation.koreksi_ke_kode_valid("AFTDVBO1", KODE, 2.0)[2])
        self.assertFalse(validation.koreksi_ke_kode_valid("AFTDVBO1", KODE, 1.0)[2])

    def test_teks_kosong_dan_penanda_gagal(self):
        self.assertEqual(validation.koreksi_ke_kode_valid("", KODE), ("", None, False))
        self.assertEqual(validation.koreksi_ke_kode_valid("[TIDAK TERBACA]", KODE)[2], False)

    def test_daftar_kode_kosong_tidak_pernah_yakin(self):
        self.assertEqual(validation.koreksi_ke_kode_valid("AKL642", []), ("AKL642", None, False))

    def test_status_kode(self):
        self.assertEqual(validation.status_kode("AKL642", KODE), "VALID")
        self.assertEqual(validation.status_kode("ZZZZZZ9", KODE), "INVALID")
        for penanda in ("", None, "[TIDAK TERBACA]", "[PERLU VERIFIKASI MANUAL]"):
            self.assertEqual(validation.status_kode(penanda, KODE), "NOT_FOUND")

    def test_keterbatasan_diketahui_awalan_kode(self):
        """
        KETERBATASAN YANG DIKETAHUI (dari pengujian 50 foto): 'AKL636EE' adalah awalan dari 'AKL636EEA'.
        Bacaan yang kehilangan huruf terakhir pada AKL636EEA cocok persis dengan AKL636EE dan DITERIMA.
        Uji ini mendokumentasikan perilaku itu agar tidak terlupa; bila perilaku diubah, uji ini harus diperbarui.
        """
        self.assertEqual(validation.koreksi_ke_kode_valid("AKL636EE", KODE), ("AKL636EE", 0.0, True))


class TestPembaca(unittest.TestCase):
    def setUp(self):
        self.ocr = OcrTiruan("AFTDWB01")
        ocr._ocr_instance = self.ocr
        rng = np.random.RandomState(0)
        self.tegak = rng.randint(60, 200, (400, 90, 3)).astype(np.uint8)
        self.lebar = _teks_terang(tinggi=120, lebar=480)

    def tearDown(self):
        ocr._ocr_instance = None

    def test_tepat_satu_panggilan_ocr(self):
        reader.baca_kode(self.tegak, KODE)
        self.assertEqual(len(self.ocr.panggilan), 1)

    def test_crop_tegak_diputar_menjadi_mendatar(self):
        reader.baca_kode(self.tegak, KODE)
        tinggi, lebar = self.ocr.panggilan[0]
        self.assertGreater(lebar, tinggi, "OCR harus menerima gambar mendatar (crop tegak diputar 90 derajat)")

    def test_crop_mendatar_tidak_diputar(self):
        reader.baca_kode(self.lebar, KODE)
        tinggi, lebar = self.ocr.panggilan[0]
        self.assertGreater(lebar, tinggi)

    def test_hasil_valid(self):
        h = reader.baca_kode(self.tegak, KODE)
        self.assertEqual((h["kode"], h["status_baca"]), ("AFTDWB01", "VALID_TERBACA"))
        self.assertEqual(h["waktu_recovery"], 0.0)
        self.assertIn("mode cepat", h["alasan"])

    def test_koreksi_o_menjadi_nol(self):
        self.ocr.teks = "AFTDWBO1"
        self.assertEqual(reader.baca_kode(self.tegak, KODE)["kode"], "AFTDWB01")

    def test_bacaan_ngawur_perlu_verifikasi_manual(self):
        self.ocr.teks = "NAMMXD"
        h = reader.baca_kode(self.tegak, KODE)
        self.assertEqual((h["kode"], h["status_baca"]), ("[PERLU VERIFIKASI MANUAL]", "PERLU_VERIFIKASI"))

    def test_bacaan_terlalu_pendek_ditolak(self):
        self.ocr.teks = "AKL6"      # 4 karakter < MIN_LEN
        self.assertEqual(reader.baca_kode(self.tegak, KODE)["kode"], "[PERLU VERIFIKASI MANUAL]")

    def test_confidence_rendah_ditolak(self):
        self.ocr.skor = 0.2
        self.assertEqual(reader.baca_kode(self.tegak, KODE)["kode"], "[PERLU VERIFIKASI MANUAL]")

    def test_tidak_ada_teks_ditolak(self):
        self.ocr.teks = ""
        self.assertEqual(reader.baca_kode(self.tegak, KODE)["kode"], "[PERLU VERIFIKASI MANUAL]")

    def test_karakter_selain_huruf_angka_dibuang(self):
        self.ocr.teks = "AKL-642 "
        self.assertEqual(reader.baca_kode(self.tegak, KODE)["kode"], "AKL642")

    def test_ambang_diteruskan(self):
        self.ocr.teks = "AFTDVBO1"      # jarak 2.0
        self.assertEqual(reader.baca_kode(self.tegak, KODE, ambang_terima=2.0)["kode"], "AFTDWB01")
        self.assertEqual(reader.baca_kode(self.tegak, KODE, ambang_terima=1.0)["kode"], "[PERLU VERIFIKASI MANUAL]")


class TestBacaanMentah(unittest.TestCase):
    """Bacaan OCR apa adanya harus tetap tersedia walau ditolak, TANPA mengubah keputusan terima atau tolak."""

    def setUp(self):
        self.ocr = OcrTiruan("AFTDWB01")
        ocr._ocr_instance = self.ocr
        self.crop = np.random.RandomState(0).randint(60, 200, (400, 90, 3)).astype(np.uint8)

    def tearDown(self):
        ocr._ocr_instance = None

    def baca(self):
        return reader.baca_kode(self.crop, KODE)

    def test_bacaan_tidak_cocok_tetap_tampil(self):
        self.ocr.teks = "NAMMXD"
        h = self.baca()
        self.assertEqual(h["kode"], "[PERLU VERIFIKASI MANUAL]")
        self.assertEqual(h["teks_mentah"], "NAMMXD")
        self.assertIn("NAMMXD", h["alasan"])
        self.assertIn("cek manual", h["alasan"])
        self.assertGreater(h["jarak_koreksi"], 2.0)

    def test_bacaan_terlalu_pendek_tetap_tampil(self):
        self.ocr.teks = "AKL6"
        h = self.baca()
        self.assertEqual((h["kode"], h["teks_mentah"]), ("[PERLU VERIFIKASI MANUAL]", "AKL6"))
        self.assertIn("terlalu pendek", h["alasan"])

    def test_bacaan_keyakinan_rendah_tetap_tampil(self):
        self.ocr.teks, self.ocr.skor = "AFTDWB01", 0.2
        h = self.baca()
        self.assertEqual(h["kode"], "[PERLU VERIFIKASI MANUAL]", "keputusan tidak boleh berubah: tetap ditolak")
        self.assertEqual(h["teks_mentah"], "AFTDWB01", "bacaan aslinya tetap dilaporkan walau ditolak")
        self.assertEqual(h["confidence_ocr"], 0.2)
        self.assertIn("keyakinan OCR rendah", h["alasan"])

    def test_tidak_ada_teks(self):
        self.ocr.teks = ""
        h = self.baca()
        self.assertEqual(h["teks_mentah"], "")
        self.assertIsNone(h["jarak_koreksi"])
        self.assertIn("tidak ada teks", h["alasan"])

    def test_bacaan_diterima_menyimpan_bacaan_asli_sebelum_koreksi(self):
        self.ocr.teks = "AFTDWBO1"            # huruf O di tempat angka nol
        h = self.baca()
        self.assertEqual((h["kode"], h["teks_mentah"]), ("AFTDWB01", "AFTDWBO1"))
        self.assertAlmostEqual(h["jarak_koreksi"], 1.0)

    def test_hampir_cocok_melaporkan_jarak(self):
        self.ocr.teks = "AFTDWROI"            # sedikit melewati batas 2,0
        h = self.baca()
        self.assertEqual(h["kode"], "[PERLU VERIFIKASI MANUAL]")
        self.assertEqual(h["teks_mentah"], "AFTDWROI")
        self.assertGreater(h["jarak_koreksi"], 2.0)
        self.assertIn("jarak terdekat", h["alasan"])

    def test_tetap_satu_panggilan_ocr(self):
        self.ocr.teks = "NAMMXD"
        self.baca()
        self.assertEqual(len(self.ocr.panggilan), 1)

    def test_baca_cepat_lama_perilakunya_tidak_berubah(self):
        """baca_cepat (dipakai pengujian 50 foto) tetap mengembalikan penanda gagal pada bacaan pendek atau ragu."""
        self.ocr.teks = "AKL6"
        self.assertEqual(reader.baca_cepat(self.crop)[:2], ("[TIDAK TERBACA]", 0.0))
        self.ocr.teks, self.ocr.skor = "AFTDWB01", 0.3
        self.assertEqual(reader.baca_cepat(self.crop)[:2], ("[TIDAK TERBACA]", 0.3))
        self.ocr.skor = 0.9
        self.assertEqual(reader.baca_cepat(self.crop)[:2], ("AFTDWB01", 0.9))


class TestOrientasi(unittest.TestCase):
    """
    deskew harus memberi hasil BENAR pada versi OpenCV mana pun. Versi lama dari arsip salah di dua hal: memutar
    ke arah yang salah, dan pada OpenCV 4.13 memutar crop mendatar 90 derajat. Uji ini akan GAGAL bila perilaku
    seperti itu muncul lagi (mis. setelah OpenCV diperbarui).
    """

    def test_teks_mendatar_tetap_mendatar(self):
        from core.orientation import deskew
        img = _teks_terang()
        lurus, sudut = deskew(img)
        self.assertGreater(lurus.shape[1], lurus.shape[0], "gambar mendatar tidak boleh menjadi tegak")
        self.assertEqual(sudut, 0.0)

    def test_kemiringan_kecil_diluruskan_ke_arah_yang_benar(self):
        from core.orientation import deskew
        for miring in (3, -3, 8, -8, 15, -15):
            with self.subTest(miring=miring):
                asli = _putar(_teks_terang(), miring, (30, 30, 30))
                lurus, _ = deskew(asli)
                self.assertGreater(lurus.shape[1], lurus.shape[0])
                self.assertLessEqual(abs(_sisa_miring(lurus)), 1.5, "sisa kemiringan setelah deskew harus mendekati nol")

    def test_kemiringan_besar_dibiarkan(self):
        from core.orientation import deskew
        asli = _putar(_teks_terang(), 30, (30, 30, 30))
        lurus, sudut = deskew(asli)
        self.assertEqual(sudut, 0.0)
        self.assertEqual(lurus.shape, asli.shape)

    def test_gambar_kosong_tidak_diubah(self):
        from core.orientation import deskew
        kosong = np.full((60, 200, 3), 200, np.uint8)
        lurus, sudut = deskew(kosong)
        self.assertEqual(sudut, 0.0)
        self.assertTrue(np.array_equal(lurus, kosong), "isi gambar kosong tidak boleh berubah")

    def test_rotate_image_90_menukar_tinggi_dan_lebar(self):
        from core.orientation import rotate_image
        hasil = rotate_image(np.zeros((400, 90, 3), np.uint8), 90)
        self.assertEqual(hasil.shape[:2], (90, 400))

    def test_putar_90_berlawanan_arah_jarum_jam(self):
        """Titik di sudut KIRI-ATAS crop tegak harus pindah ke KIRI-BAWAH setelah diputar 90 derajat berlawanan arah jarum jam."""
        from core.orientation import rotate_image
        img = np.zeros((400, 90, 3), np.uint8)
        img[0:40, 0:40] = 255                          # blok putih di kiri-atas
        hasil = rotate_image(img, 90)[:, :, 0]
        h, w = hasil.shape
        self.assertGreater(hasil[h // 2:, :w // 2].mean(), hasil[:h // 2, w // 2:].mean() + 5)   # putih di kiri-BAWAH


class TestDetektor(unittest.TestCase):
    def test_perkecil_bila_besar(self):
        besar = np.zeros((3000, 4000, 3), np.uint8)
        hasil = detector.perkecil_bila_besar(besar, 1600)
        self.assertEqual(hasil.shape[:2], (1200, 1600))
        kecil = np.zeros((480, 640, 3), np.uint8)
        self.assertIs(detector.perkecil_bila_besar(kecil, 1600), kecil)       # tidak diubah, objek yang sama

    def test_perkecil_menjaga_rasio_gambar_tegak(self):
        hasil = detector.perkecil_bila_besar(np.zeros((4000, 2000, 3), np.uint8), 1600)
        self.assertEqual(hasil.shape[:2], (1600, 800))

    def test_crop_gabungan_union_dan_padding(self):
        frame = np.zeros((500, 600, 3), np.uint8)
        dets = [{"bbox": (100, 100, 200, 200), "confidence": 0.9}, {"bbox": (300, 150, 400, 300), "confidence": 0.5}]
        crop, bbox = detector.crop_gabungan(frame, dets, padding=8)
        self.assertEqual(bbox, (92, 92, 408, 308))
        self.assertEqual(crop.shape[:2], (216, 316))

    def test_crop_gabungan_dibatasi_tepi_gambar(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        crop, bbox = detector.crop_gabungan(frame, [{"bbox": (0, 0, 100, 100), "confidence": 0.9}], padding=8)
        self.assertEqual(bbox, (0, 0, 100, 100))
        self.assertEqual(crop.shape[:2], (100, 100))

    def test_crop_gabungan_tanpa_deteksi(self):
        self.assertEqual(detector.crop_gabungan(np.zeros((10, 10, 3), np.uint8), []), (None, None))

    def test_gambar_kotak_tidak_mengubah_aslinya(self):
        frame = np.zeros((200, 300, 3), np.uint8)
        vis = detector.gambar_kotak_deteksi(frame, [{"bbox": (10, 40, 100, 120), "confidence": 0.9}])
        self.assertEqual(vis.shape, frame.shape)
        self.assertEqual(int(frame.sum()), 0)
        self.assertGreater(int(vis.sum()), 0)

    def test_model_tidak_ada_memberi_galat_yang_jelas(self):
        with self.assertRaises(detector.ModelTidakDitemukan) as ctx:
            detector.get_yolo_model("/tidak/ada/model.pt")
        self.assertIn("models_ai", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
