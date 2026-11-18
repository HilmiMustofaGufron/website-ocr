"""
services/preprocessing.py
============================
TANGGUNG JAWAB:
Image Quality Analysis (IQA) dan Adaptive Preprocessing terhadap hasil
crop sebelum masuk ke OCR.

Dipindahkan (bukan ditulis ulang dari nol) dari notebook riset
`PaddleOCR_stempel_optimized_IQA.ipynb` (cell 3 & 4b), TANPA mengubah
algoritma — hanya direstrukturisasi jadi modul reusable.

KEPUTUSAN DESAIN (dipertahankan dari notebook asli):
- Pemilihan teknik preprocessing 100% berbasis analisis karakteristik
  citra (brightness, contrast, noise, sharpness, saturation) via OpenCV,
  BUKAN dengan mencoba tiap teknik ke OCR satu per satu. Ini membuat
  pemilihan preprocessing berbiaya 0 panggilan OCR (dulu bisa sampai 8x
  sebelum notebook ini dioptimasi).
- 8 teknik preprocessing disediakan sebagai kandidat (SEMUA_PREP), sistem
  skor menambah nilai ke teknik yang relevan berdasarkan kondisi citra.
"""

import math
import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Kumpulan teknik preprocessing (kandidat)
# ---------------------------------------------------------------------------

def prep_asli(img):
    return img


def prep_gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def prep_clahe(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(g)


def prep_threshold(img):
    g = prep_clahe(img)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 31, -5)


def prep_sharpen(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    # Bilateral filter untuk menghaluskan noise tanpa merusak tepi.
    g = cv2.bilateralFilter(g, 9, 75, 75)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(g, -1, kernel)


def prep_denoise_threshold(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    g = cv2.bilateralFilter(g, 9, 75, 75)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    g = clahe.apply(g)
    return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 31, -5)


def prep_morph(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    g = clahe.apply(g)
    # Morphological opening untuk menghilangkan noise bintik kecil di latar belakang.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(g, cv2.MORPH_OPEN, kernel)


def prep_color_boost(img):
    # HSV untuk memanipulasi saturasi warna (berguna untuk stempel berwarna).
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s_eq = cv2.equalizeHist(s)
    enhanced_hsv = cv2.merge([h, s_eq, v])
    enhanced_bgr = cv2.cvtColor(enhanced_hsv, cv2.COLOR_HSV2BGR)

    g = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(g)


def prep_emboss_adaptif(img):
    """
    Preprocessing khusus teks TIMBUL/EMBOSSED di permukaan logam, di mana
    huruf tidak punya kontras WARNA dengan latar (beda dari tinta cetak) --
    kontrasnya cuma dari bayangan HALUS & LOKAL akibat cahaya. Metrik IQA
    global (brightness/contrast/sharpness/saturation) tidak bisa mendeteksi
    kasus ini karena kontras globalnya bisa saja normal, padahal kontras
    LOKAL antar-goresan huruf sangat rendah.

    Ditambahkan berdasarkan temuan pengujian nyata (bukan dari notebook
    riset awal) -- lihat services/ocr_engine.py dan services/recovery.py
    untuk perbaikan terkait yang juga berasal dari temuan yang sama.

    Pendekatan: adaptiveThreshold (bukan Otsu/threshold global) supaya
    tiap area kecil dibandingkan ke tetangga LOKAL-nya sendiri, jauh lebih
    peka menangkap goresan emboss tipis dibanding threshold global manapun.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    g = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g)
    biner = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 5)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    return cv2.morphologyEx(biner, cv2.MORPH_OPEN, kernel)


# Urutan dict SENGAJA disusun dengan 'clahe' di depan (bukan abjad/acak),
# supaya early-stop di pemilihan preprocessing sering terpicu di awal.
# 'emboss_adaptif' ditambahkan di akhir sebagai preprocessing tambahan
# hasil temuan pengujian nyata (bukan dari notebook riset awal).
SEMUA_PREP = {
    "clahe": prep_clahe,
    "denoise_thresh": prep_denoise_threshold,
    "threshold": prep_threshold,
    "sharpen": prep_sharpen,
    "morph": prep_morph,
    "gray2x": prep_gray,
    "color_boost": prep_color_boost,
    "asli": prep_asli,
    "emboss_adaptif": prep_emboss_adaptif,
}


# ---------------------------------------------------------------------------
# Image Quality Analysis (IQA) — murni OpenCV, TANPA OCR
# ---------------------------------------------------------------------------

# Ambang batas (threshold) untuk menentukan kondisi "kurang ideal".
# Kalibrasi kasar untuk foto stempel/teks cetak biasa.
AMBANG_IQA = {
    "brightness_rendah": 95,
    "brightness_tinggi": 190,
    "contrast_rendah": 38,
    "noise_tinggi": 6.0,
    "sharpness_rendah": 120,
    "saturation_rendah": 40,
}


def analyze_quality(img):
    """
    Hitung 5 parameter kualitas citra dengan OpenCV (TANPA OCR):
    brightness, contrast, noise, sharpness, saturation.

    Args:
        img: numpy.ndarray, citra BGR hasil crop dari bounding box YOLO.

    Returns:
        dict: {"brightness", "contrast", "noise", "sharpness", "saturation"}
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) if len(img.shape) == 3 else None

    brightness = float(gray.mean())
    contrast = float(gray.std())

    # Sharpness: variansi Laplacian - semakin tinggi berarti semakin tajam.
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Noise: estimasi cepat ala Immerkaer (1996).
    H, W = gray.shape
    kernel_noise = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    konvolusi = cv2.filter2D(gray.astype(np.float64), -1, kernel_noise)
    noise = float(
        np.sum(np.abs(konvolusi)) * math.sqrt(0.5 * math.pi)
        / (6 * max(W - 2, 1) * max(H - 2, 1))
    )

    saturation = float(hsv[:, :, 1].mean()) if hsv is not None else 0.0

    return {
        "brightness": brightness,
        "contrast": contrast,
        "noise": noise,
        "sharpness": sharpness,
        "saturation": saturation,
    }


def _score_preprocessing(metrik, ambang=AMBANG_IQA):
    """Sistem skoring murni dari IQA (bukan OCR) untuk pilih preprocessing terbaik."""
    skor = {nama: 0.0 for nama in SEMUA_PREP}

    gelap = metrik["brightness"] < ambang["brightness_rendah"]
    terlalu_terang = metrik["brightness"] > ambang["brightness_tinggi"]
    kontras_rendah = metrik["contrast"] < ambang["contrast_rendah"]
    noise_tinggi = metrik["noise"] > ambang["noise_tinggi"]
    buram = metrik["sharpness"] < ambang["sharpness_rendah"]
    pudar = metrik["saturation"] < ambang["saturation_rendah"]

    if gelap or kontras_rendah:
        skor["clahe"] += 2.0
        skor["denoise_thresh"] += 1.0
        skor["threshold"] += 1.0
        skor["morph"] += 1.0
        skor["color_boost"] += 0.5

    if terlalu_terang:
        skor["threshold"] += 1.5
        skor["denoise_thresh"] += 1.0

    if noise_tinggi:
        skor["denoise_thresh"] += 3.0
        skor["morph"] += 2.0
        skor["sharpen"] += 1.0

    if buram:
        skor["sharpen"] += 3.0
        skor["denoise_thresh"] += 0.5

    if pudar:
        skor["color_boost"] += 3.0
        # Permukaan logam biasanya juga desaturasi (pudar) -- kasus ini
        # kerap tumpang tindih dengan teks embossed. Beri skor supaya
        # emboss_adaptif juga jadi kandidat kuat, bukan cuma color_boost.
        skor["emboss_adaptif"] += 2.0

    if not (gelap or terlalu_terang or kontras_rendah or noise_tinggi or buram):
        skor["gray2x"] += 1.5
        skor["asli"] += 0.5
        # Kontras & sharpness GLOBAL normal (tidak ke-flag gelap/buram/
        # noisy) tapi teks tetap bisa gagal terbaca kalau kontrasnya cuma
        # rendah secara LOKAL (goresan emboss tipis) -- metrik global tidak
        # bisa mendeteksi ini. emboss_adaptif tetap diberi skor dasar di
        # sini supaya selalu jadi salah satu kandidat yang dicoba.
        skor["emboss_adaptif"] += 1.0

    return skor


def adaptive_preprocess(img, debug=False):
    """
    Pilih & terapkan teknik preprocessing terbaik berdasarkan IQA saja.
    TIDAK memanggil PaddleOCR sama sekali di fungsi ini.

    Args:
        img: numpy.ndarray, citra BGR hasil crop.
        debug: bool, cetak detail skor tiap teknik jika True.

    Returns:
        tuple: (nama_prep_terbaik: str, metrik_iqa: dict, skor_semua: dict)
        Gunakan SEMUA_PREP[nama_prep_terbaik] untuk mendapatkan fungsinya,
        atau panggil apply_preprocessing(img, nama_prep_terbaik).
    """
    metrik = analyze_quality(img)
    skor_semua = _score_preprocessing(metrik)
    nama_terbaik = max(skor_semua, key=lambda k: skor_semua[k])

    if debug:
        print("  Image Quality Analysis:")
        print(
            f"    brightness={metrik['brightness']:.1f}  contrast={metrik['contrast']:.1f}  "
            f"noise={metrik['noise']:.2f}  sharpness={metrik['sharpness']:.1f}  "
            f"saturation={metrik['saturation']:.1f}"
        )
        print("  Skor tiap preprocessing (dari IQA, TANPA OCR):")
        for nama, s in sorted(skor_semua.items(), key=lambda x: -x[1]):
            tanda = "  <- terpilih" if nama == nama_terbaik else ""
            print(f"    {nama:14s}: skor={s:4.1f}{tanda}")

    return nama_terbaik, metrik, skor_semua


def apply_preprocessing(img, nama_prep):
    """Menerapkan satu teknik preprocessing (dari SEMUA_PREP) ke citra."""
    return SEMUA_PREP[nama_prep](img)
