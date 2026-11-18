"""
services/orientation.py
=========================
TANGGUNG JAWAB:
Orientation Analysis — mendeteksi dan mengoreksi rotasi/kemiringan teks
kode produk hasil crop, SEBELUM dibaca OCR.

Dipindahkan dari notebook riset (cell 5), TANPA mengubah algoritma.
Modul ini murni operasi citra (OpenCV) dan TIDAK memanggil PaddleOCR —
pemanggilan OCR dengan orientasi hasil modul ini dilakukan di
services/ocr_engine.py (bagian orkestrasi), sesuai prinsip Separation
of Concerns.
"""

import cv2
import numpy as np


# Koreksi hanya dilakukan untuk kemiringan kecil. PaddleOCR sendiri sudah menangani teks yang agak miring,
# sedangkan "koreksi" besar lebih mungkin berasal dari pantulan cahaya daripada kemiringan sungguhan
# (nilai 20 derajat adalah pilihan konservatif, bukan hasil pengujian).
BATAS_KOREKSI_DERAJAT = 20.0


def deskew(img):
    """
    Meluruskan kemiringan teks otomatis memakai minAreaRect.

    PERUBAHAN DARI VERSI PENGUJIAN: konvensi sudut cv2.minAreaRect berbeda antar versi OpenCV. Versi lama
    fungsi ini benar pada OpenCV 4.10 tetapi MEMUTAR 90 DERAJAT crop yang sudah mendatar pada OpenCV 4.13.
    Versi lama juga memutar ke ARAH YANG SALAH (kemiringan +3 derajat menjadi -6 derajat). Versi ini menormalkan
    sudut garis panjang kotak ke rentang (-45, 45] derajat dan memutar ke arah yang benar, sehingga sisa kemiringan
    mendekati nol dan hasilnya sama pada kedua versi OpenCV. Fungsi ini hanya dipakai untuk crop yang SUDAH mendatar; crop tegak memakai rotate_image
    (cabang itulah yang dipakai di seluruh pengujian 50 foto, jadi hasil uji tidak terpengaruh).

    Args:
        img: numpy.ndarray, citra BGR hasil crop.

    Returns:
        tuple: (gambar_lurus: numpy.ndarray, sudut: float)
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g)
    _, biner = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    koordinat = np.column_stack(np.where(biner > 0))          # (baris, kolom)
    if len(koordinat) < 50:
        return img, 0.0

    titik_xy = koordinat[:, ::-1].astype(np.float32)           # (x, y)
    (_cx, _cy), (lebar_k, tinggi_k), sudut = cv2.minAreaRect(titik_xy)
    if lebar_k < tinggi_k:
        sudut += 90.0                                          # sudut sisi PANJANG kotak terhadap sumbu-x
    sudut = ((sudut + 45.0) % 90.0) - 45.0                     # lipat ke [-45, 45)
    if abs(sudut) < 0.05:
        sudut = 0.0
    if abs(sudut) > BATAS_KOREKSI_DERAJAT:
        return img, 0.0                                        # kemungkinan bukan kemiringan teks: biarkan apa adanya

    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), sudut, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    W, H = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += (W / 2) - w // 2
    M[1, 2] += (H / 2) - h // 2
    lurus = cv2.warpAffine(
        img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return lurus, sudut


def rotate_image(img, angle):
    """Memutar gambar `angle` derajat tanpa memotong sudut (canvas menyesuaikan)."""
    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    W, H = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += (W / 2) - w // 2
    M[1, 2] += (H / 2) - h // 2
    return cv2.warpAffine(
        img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def detect_orientation_candidates(img):
    """
    Perkirakan kemungkinan arah teks (horizontal vs vertikal) dari bentuk
    blok konten (rasio lebar:tinggi bounding-box piksel non-latar hasil
    threshold Otsu) — TANPA OCR sama sekali. Dipakai hanya untuk
    mempersempit sudut kandidat yang layak dicoba saat OCR pertama (hasil
    deskew) belum cukup yakin.

    Args:
        img: numpy.ndarray, citra BGR.

    Returns:
        list[int]: sudut kandidat (derajat), urutan dari yang paling mungkin benar.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g)
    _, biner = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    koordinat = np.column_stack(np.where(biner > 0))
    if len(koordinat) < 50:
        return [180, 90, -90]  # info bentuk tidak cukup -> urutan umum

    y0, x0 = koordinat.min(axis=0)
    y1, x1 = koordinat.max(axis=0)
    tinggi_blok, lebar_blok = (y1 - y0), (x1 - x0)

    if tinggi_blok > lebar_blok * 1.3:
        # Blok konten memanjang vertikal -> teks kemungkinan tegak (difoto miring 90 derajat).
        return [90, -90, 180]
    if lebar_blok > tinggi_blok * 1.3:
        # Blok konten memanjang horizontal -> teks kemungkinan sudah searah baca normal.
        return [180, 90, -90]
    # Rasio mendekati persegi -> ambigu, coba urutan paling umum dulu.
    return [180, 90, -90]
