"""
core/ocr.py
===========
PaddleOCR dan penyaringan hasil bacaannya.

Isi fungsi baca_paddleocr() dan pengaturan PaddleOCR di sini SAMA PERSIS dengan yang dipakai pada pengujian
50 foto (hasil: 28 benar), supaya hasil uji tetap berlaku untuk aplikasi ini.

PaddleOCR dibuat SEKALI saja (lazy singleton): memuatnya ulang tiap permintaan akan sangat lambat.
"""

import cv2
import numpy as np

from core.preprocessing import prep_clahe

# Whitelist karakter kode produk (PaddleOCR tidak punya parameter allowlist bawaan,
# jadi diterapkan manual sesudah hasil OCR mentah).
KARAKTER_VALID = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

_ocr_instance = None  # singleton, lihat get_ocr_instance()


def get_ocr_instance():
    """
    Mengembalikan instance PaddleOCR, dibuat hanya sekali sepanjang umur proses.

    CATATAN: PaddlePaddle >= 3.3.0 punya bug kompatibilitas oneDNN/MKL-DNN pada inferensi CPU
    ("ConvertPirAttribute2RuntimeAttribute not support"). Karena itu enable_mkldnn=False dan
    requirements.txt memakai paddlepaddle==3.2.0 + paddleocr==3.3.0.
    """
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR

        _ocr_instance = PaddleOCR(
            use_doc_orientation_classify=False,  # tidak perlu untuk crop kecil
            use_doc_unwarping=False,
            use_textline_orientation=True,       # tetap deteksi orientasi baris 0/180 derajat
            enable_mkldnn=False,                 # hindari bug oneDNN/PIR di PaddlePaddle >= 3.3.0
            lang="en",
        )
    return _ocr_instance


def baca_paddleocr(img, prep=prep_clahe):
    """
    Menjalankan satu preprocessing lalu SATU kali panggilan PaddleOCR.

    Returns:
        tuple: (teks: str, confidence_rata2: float)
    """
    proc = prep(img)
    # PaddleOCR mengharapkan gambar BGR 3 channel.
    if len(proc.shape) == 2:
        proc_bgr = cv2.cvtColor(proc, cv2.COLOR_GRAY2BGR)
    else:
        proc_bgr = proc

    ocr = get_ocr_instance()
    hasil = ocr.predict(proc_bgr)
    if not hasil:
        return "", 0.0

    res = hasil[0]
    teks_list = res.get("rec_texts", [])
    skor_list = res.get("rec_scores", [])
    poligon_list = res.get("rec_polys", res.get("dt_polys", []))

    if not teks_list:
        return "", 0.0

    # Urutkan kiri ke kanan berdasarkan titik-x terkecil tiap kotak.
    if len(poligon_list) == len(teks_list):
        urutan = sorted(range(len(teks_list)), key=lambda i: min(p[0] for p in poligon_list[i]))
    else:
        urutan = range(len(teks_list))

    potongan, confs = [], []
    for i in urutan:
        teks_bersih = "".join(c for c in teks_list[i].upper() if c in KARAKTER_VALID)
        if teks_bersih:
            potongan.append(teks_bersih)
            confs.append(skor_list[i])

    teks = "".join(potongan)
    conf = float(np.mean(confs)) if confs else 0.0
    return teks, conf
