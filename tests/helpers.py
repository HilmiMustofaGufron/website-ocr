"""
tests/helpers.py
================
Perlengkapan uji bersama. YOLO dan PaddleOCR diganti objek tiruan (agar uji berjalan cepat dan tanpa model),
dan setiap uji memakai database, folder unggahan, dan folder ekspor SEMENTARA sendiri.
"""

import os
import shutil
import sys
import tempfile
import threading
import types
import unittest

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

PASSWORD_UJI = "rahasia123"


class _Angka:
    def __init__(self, v):
        self.v = v

    def item(self):
        return self.v

    def tolist(self):
        return self.v


class _Kotak:
    def __init__(self, xyxy, conf):
        self.xyxy = [_Angka(list(xyxy))]
        self.conf = [_Angka(conf)]


class YoloTiruan:
    """YOLO tiruan. `kotak` = list (x1,y1,x2,y2,conf) dalam PECAHAN lebar/tinggi gambar; kosong = tidak ada objek."""

    def __init__(self):
        self.kotak = [(0.20, 0.30, 0.50, 0.85, 0.88)]   # satu kotak TEGAK
        self.dilihat = []        # ukuran (tinggi, lebar) gambar yang diterima, untuk diperiksa
        self.lock = threading.Lock()

    def predict(self, frame, conf=0.4, iou=0.7, imgsz=640, verbose=False):
        h, w = frame.shape[:2]
        with self.lock:
            self.dilihat.append((h, w))
            kotak = list(self.kotak)
        boxes = [_Kotak((int(a * w), int(b * h), int(c * w), int(d * h)), s) for a, b, c, d, s in kotak if s >= conf]
        return [types.SimpleNamespace(boxes=boxes)]


class OcrTiruan:
    """PaddleOCR tiruan. Mengembalikan `teks` yang diatur, dan mencatat ukuran gambar tiap panggilan."""

    def __init__(self, teks="AFTDWB01", skor=0.91):
        self.teks = teks
        self.skor = skor
        self.panggilan = []

    def predict(self, img):
        self.panggilan.append(img.shape[:2])
        if not self.teks:
            return [{"rec_texts": [], "rec_scores": [], "rec_polys": []}]
        poligon = np.array([[0, 0], [60, 0], [60, 10], [0, 10]])
        return [{"rec_texts": [self.teks], "rec_scores": [self.skor], "rec_polys": [poligon]}]


class KasusAplikasi(unittest.TestCase):
    """Dasar semua uji aplikasi: aplikasi baru + database sementara + YOLO/OCR tiruan + akun uji."""

    KODE_AWAL = ("AFTDWB01", "AKL636EE", "AKL636EEA", "AKL642")
    BUAT_MODEL = True

    def setUp(self):
        from core import detector, ocr
        from services import auth, database, scan_state

        self.tmp = tempfile.mkdtemp(prefix="uji_gudang_")
        self.path_model = os.path.join(self.tmp, "model_tiruan.pt")
        if self.BUAT_MODEL:
            with open(self.path_model, "wb") as f:
                f.write(b"bukan model asli")
        overrides = {
            "DATABASE_PATH": os.path.join(self.tmp, "uji.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "uploads"),
            "EXPORT_FOLDER": os.path.join(self.tmp, "exports"),
            "LOG_FOLDER": os.path.join(self.tmp, "logs"),
            "MODEL_YOLO_PATH": self.path_model,
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": PASSWORD_UJI,
            "SECRET_KEY": "kunci-uji",
        }
        from app import create_app

        self.app = create_app("testing", overrides=overrides)
        self.client = self.app.test_client()

        self.yolo = YoloTiruan()
        self.ocr = OcrTiruan()
        detector._models.clear()
        if self.BUAT_MODEL:
            detector._models[self.path_model] = self.yolo
        ocr._ocr_instance = self.ocr

        auth.reset_semua_percobaan()
        database.invalidate_cache_kode()
        scan_state.state_machine_aktif.reset()

        with self.app.app_context():
            for kode in self.KODE_AWAL:
                database.create_master_kode({"kode": kode, "keterangan": "uji"})

    def tearDown(self):
        from core import detector, ocr
        from services import camera

        camera.stop_stream()
        for h in list(self.app.logger.handlers):      # tutup berkas log sementara (penting di Windows)
            h.close()
            self.app.logger.removeHandler(h)
        detector._models.clear()
        ocr._ocr_instance = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------- bantuan ----------------
    def login(self, client=None, username="admin", password=PASSWORD_UJI):
        c = client or self.client
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf_token"]
        return c.post("/login", data={"username": username, "password": password, "csrf_token": token})

    def masuk(self):
        """Login lalu mengembalikan header CSRF untuk permintaan berikutnya."""
        r = self.login()
        self.assertEqual(r.status_code, 302, "login uji harus berhasil")
        with self.client.session_transaction() as s:
            return {"X-CSRF-Token": s["csrf_token"]}

    def foto_jpg(self, tinggi=480, lebar=640, acak=1):
        import cv2

        gambar = np.random.RandomState(acak).randint(0, 255, (tinggi, lebar, 3)).astype(np.uint8)
        ok, buf = cv2.imencode(".jpg", gambar)
        self.assertTrue(ok)
        return buf.tobytes()

    def kirim_foto(self, headers, data=None, nama="foto.jpg", **kw):
        import io

        return self.client.post("/scan/image", data={"file": (io.BytesIO(data or self.foto_jpg(**kw)), nama)},
                                headers=headers, content_type="multipart/form-data")
