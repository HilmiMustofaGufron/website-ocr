"""
tests/test_kamera.py -- kamera, pindai langsung, dan mesin status. Kamera diganti BERKAS VIDEO buatan sendiri
(cv2.VideoCapture membaca berkas video sama seperti membaca webcam).
"""

import os
import threading
import time
import unittest

import cv2
import numpy as np

from tests.helpers import KasusAplikasi


def buat_video(path, jumlah_frame=60, lebar=320, tinggi=240):
    penulis = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (lebar, tinggi))
    if not penulis.isOpened():
        return False
    rng = np.random.RandomState(0)
    for i in range(jumlah_frame):
        frame = rng.randint(40, 200, (tinggi, lebar, 3)).astype(np.uint8)
        cv2.putText(frame, str(i), (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        penulis.write(frame)
    penulis.release()
    return os.path.isfile(path) and os.path.getsize(path) > 0


def tunggu(kondisi, detik=5.0):
    batas = time.time() + detik
    while time.time() < batas:
        if kondisi():
            return True
        time.sleep(0.03)
    return False


class DasarKamera(KasusAplikasi):
    def setUp(self):
        super().setUp()
        self.video = os.path.join(self.tmp, "kamera.avi")
        if not buat_video(self.video):
            self.skipTest("codec MJPG tidak tersedia di lingkungan ini")
        self.h = self.masuk()

    def mulai_kamera_berulang(self):
        from services import camera
        self.assertTrue(camera.start_stream(self.video, loop_berkas=True))
        self.assertTrue(tunggu(lambda: camera.get_latest_frame() is not None), "frame pertama tidak datang")


class TestKamera(DasarKamera):
    def test_frame_jpeg_dan_status(self):
        self.mulai_kamera_berulang()
        r = self.client.get("/camera/frame")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/jpeg")
        self.assertTrue(r.data.startswith(b"\xff\xd8"))
        st = self.client.get("/camera/status").get_json()
        self.assertTrue(st["aktif"])
        self.assertTrue(tunggu(lambda: self.client.get("/camera/status").get_json()["fps"] > 0, 3.0), "FPS harus terhitung")

    def test_frame_belum_ada_503(self):
        r = self.client.get("/camera/frame")
        self.assertEqual(r.status_code, 503)
        self.assertIn("error", r.get_json())

    def test_start_lewat_route_menyimpan_sumber_di_pengaturan(self):
        r = self.client.post("/camera/start", json={"source": self.video}, headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "started")
        with self.app.app_context():
            from services import database
            self.assertEqual(database.get_settings().kamera_aktif, self.video)

    def test_sumber_angka_dalam_teks_menjadi_indeks_perangkat(self):
        from services import camera
        dicatat = {}
        asli = camera.start_stream
        camera.start_stream = lambda source, on_terputus=None, loop_berkas=False: (dicatat.update(s=source) or True)
        try:
            self.client.post("/camera/start", json={"source": "2"}, headers=self.h)
            self.assertEqual(dicatat["s"], 2)
            self.assertIsInstance(dicatat["s"], int)
            self.client.post("/camera/start", json={"source": 1.0}, headers=self.h)
            self.assertEqual(dicatat["s"], 1)
        finally:
            camera.start_stream = asli

    def test_sumber_tidak_valid_400(self):
        for sumber in (True, ["a"], {"x": 1}):
            with self.subTest(sumber=sumber):
                self.assertEqual(self.client.post("/camera/start", json={"source": sumber}, headers=self.h).status_code, 400)

    def test_kamera_tidak_bisa_dibuka_500_dengan_pesan(self):
        r = self.client.post("/camera/start", json={"source": os.path.join(self.tmp, "tidak_ada.avi")}, headers=self.h)
        self.assertEqual(r.status_code, 500)
        self.assertIn("Tidak bisa membuka kamera", r.get_json()["pesan_error"])
        self.assertFalse(self.client.get("/camera/status").get_json()["aktif"])

    def test_stop_menghentikan_dan_mengosongkan_frame(self):
        self.mulai_kamera_berulang()
        self.assertEqual(self.client.post("/camera/stop", headers=self.h).get_json()["status"], "stopped")
        self.assertFalse(self.client.get("/camera/status").get_json()["aktif"])
        self.assertEqual(self.client.get("/camera/frame").status_code, 503)

    def test_mulai_ulang_menggantikan_koneksi_lama(self):
        from services import camera
        self.mulai_kamera_berulang()
        self.assertTrue(camera.start_stream(self.video, loop_berkas=True))
        self.assertTrue(tunggu(lambda: camera.get_latest_frame() is not None))
        self.assertTrue(camera.get_camera_status()["aktif"])

    def test_putus_sendiri_membuat_satu_notifikasi_kamera_terputus(self):
        buat_video(self.video, jumlah_frame=8)                       # video pendek: habis sendiri = "terputus"
        self.client.post("/camera/start", json={"source": self.video}, headers=self.h)
        self.assertTrue(tunggu(lambda: not self.client.get("/camera/status").get_json()["aktif"]), "kamera seharusnya terputus")
        self.assertTrue(tunggu(lambda: self.client.get("/notifications/").get_json()["jumlah_belum_dibaca"] >= 1))
        n = self.client.get("/notifications/").get_json()["notifikasi"]
        self.assertEqual([x["tipe"] for x in n], ["kamera_terputus"])
        self.assertIn("terputus", self.client.get("/camera/status").get_json()["pesan_error"])

    def test_dihentikan_operator_tidak_dianggap_terputus(self):
        self.client.post("/camera/start", json={"source": self.video}, headers=self.h)
        time.sleep(0.2)
        self.client.post("/camera/stop", headers=self.h)
        time.sleep(0.3)
        self.assertEqual(self.client.get("/notifications/").get_json()["jumlah_belum_dibaca"], 0)


class TestPindaiLangsung(DasarKamera):
    def _panggil(self, n=1):
        hasil = []
        for _ in range(n):
            hasil.append(self.client.post("/scan/live", headers=self.h).get_json())
        return hasil

    def _jumlah_riwayat(self):
        return len(self.client.get("/history/search").get_json())

    def test_tanpa_frame_503(self):
        r = self.client.post("/scan/live", headers=self.h)
        self.assertEqual(r.status_code, 503)

    def test_auto_scan_mati(self):
        self.mulai_kamera_berulang()
        self.client.post("/settings/", json={"auto_scan": False}, headers=self.h)
        self.assertEqual(self.client.post("/scan/live", headers=self.h).get_json()["status"], "auto_scan_off")
        self.assertEqual(len(self.ocr.panggilan), 0)

    def test_urutan_status_dan_satu_kali_scan_per_objek(self):
        self.mulai_kamera_berulang()
        hasil = self._panggil(5)
        self.assertEqual([h["state"] for h in hasil], ["OBJECT_DETECTED", "OBJECT_DETECTED", "SUDAH_DISCAN", "SUDAH_DISCAN", "SUDAH_DISCAN"])
        self.assertEqual([h["scan_dipicu"] for h in hasil], [False, False, True, False, False])
        self.assertEqual(hasil[2]["hasil"]["status"], "VALID")
        self.assertEqual(self._jumlah_riwayat(), 1, "objek yang sama tidak boleh dicatat berkali-kali")
        self.assertEqual(len(self.ocr.panggilan), 1, "OCR hanya sekali per objek")

    def test_ocr_tidak_dipanggil_selama_belum_stabil(self):
        self.mulai_kamera_berulang()
        self._panggil(2)
        self.assertEqual(len(self.ocr.panggilan), 0)

    def test_objek_hilang_sebelum_stabil_dianggap_noise(self):
        self.mulai_kamera_berulang()
        self._panggil(2)
        self.yolo.kotak = []
        self.assertEqual(self._panggil(1)[0]["state"], "IDLE")
        self.assertEqual(self._jumlah_riwayat(), 0)

    def test_objek_diangkat_lalu_objek_baru_discan_lagi(self):
        self.mulai_kamera_berulang()
        self._panggil(3)                                     # scan pertama
        kotak = self.yolo.kotak
        self.yolo.kotak = []
        hasil = self._panggil(5)                              # 5 frame kosong -> IDLE
        self.assertEqual([h["state"] for h in hasil], ["SUDAH_DISCAN"] * 4 + ["IDLE"])
        self.yolo.kotak = kotak
        self.ocr.teks = "AKL642"
        baru = self._panggil(3)
        self.assertTrue(baru[2]["scan_dipicu"])
        self.assertEqual(baru[2]["hasil"]["kode"], "AKL642")
        self.assertEqual(self._jumlah_riwayat(), 2)

    def test_kedipan_singkat_tidak_memicu_scan_ulang(self):
        self.mulai_kamera_berulang()
        self._panggil(3)
        kotak = self.yolo.kotak
        self.yolo.kotak = []
        self._panggil(2)                                      # hanya 2 frame kosong (< 5)
        self.yolo.kotak = kotak
        self._panggil(4)
        self.assertEqual(self._jumlah_riwayat(), 1)

    def test_status_scan_terakhir(self):
        self.mulai_kamera_berulang()
        self.assertIsNone(self.client.get("/scan/status").get_json()["hasil_scan_terakhir"])
        self._panggil(3)
        st = self.client.get("/scan/status").get_json()
        self.assertEqual(st["state"], "SUDAH_DISCAN")
        self.assertEqual(st["hasil_scan_terakhir"]["status"], "VALID")

    def test_hentikan_kamera_mereset_mesin_status(self):
        self.mulai_kamera_berulang()
        self._panggil(3)
        self.client.post("/camera/stop", headers=self.h)
        st = self.client.get("/scan/status").get_json()
        self.assertEqual(st["state"], "IDLE")
        self.assertIsNone(st["hasil_scan_terakhir"])

    def test_kegagalan_saat_scan_tidak_membuat_mesin_macet(self):
        self.mulai_kamera_berulang()
        self._panggil(2)
        asli = self.ocr.predict
        self.ocr.predict = lambda img: (_ for _ in ()).throw(RuntimeError("OCR rusak"))
        self.assertEqual(self.client.post("/scan/live", headers=self.h).status_code, 500)
        self.assertEqual(self.client.get("/scan/status").get_json()["state"], "IDLE", "tidak boleh macet di SCANNING")
        self.ocr.predict = asli
        hasil = self._panggil(3)
        self.assertTrue(hasil[2]["scan_dipicu"])

    def test_dua_permintaan_bersamaan_tidak_menghasilkan_dua_scan(self):
        self.mulai_kamera_berulang()
        self._panggil(2)                                      # siap: satu frame lagi memicu scan
        c2 = self.app.test_client()
        self.login(client=c2)
        with c2.session_transaction() as s:
            h2 = {"X-CSRF-Token": s["csrf_token"]}
        hasil, gerbang = [], threading.Barrier(2)

        def kirim(klien, header):
            gerbang.wait()
            hasil.append(klien.post("/scan/live", headers=header).get_json())

        t = [threading.Thread(target=kirim, args=(self.client, self.h)), threading.Thread(target=kirim, args=(c2, h2))]
        [x.start() for x in t]
        [x.join(15) for x in t]
        self.assertEqual(len(hasil), 2)
        self.assertEqual(sum(1 for x in hasil if x["scan_dipicu"]), 1, "tepat SATU permintaan yang boleh memicu scan")
        self.assertEqual(self._jumlah_riwayat(), 1)


class TestPindaiLangsungTanpaModel(DasarKamera):
    BUAT_MODEL = False

    def test_pesan_jelas_dan_mesin_tidak_macet(self):
        self.mulai_kamera_berulang()
        for _ in range(2):
            r = self.client.post("/scan/live", headers=self.h)
            self.assertEqual(r.status_code, 503)
            self.assertIn("models_ai", r.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
