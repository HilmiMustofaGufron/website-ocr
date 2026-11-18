"""
core/reader.py
==============
MODE CEPAT: satu kali pembacaan, tanpa jalur cadangan.

Alur untuk satu crop:
  1. Pilih SATU preprocessing dengan skor kualitas gambar (IQA) tertinggi (IQA tidak memanggil OCR).
  2. Crop tegak (tinggi > lebar) diputar 90 derajat berlawanan arah jarum jam; crop yang sudah mendatar
     hanya diluruskan (deskew).
  3. SATU kali PaddleOCR.
  4. Cocokkan ke daftar kode valid. Cocok -> kode diterima. Tidak cocok -> verifikasi manual.

Hasil pengujian (50 foto berkunci jawaban, foto yang sama untuk semua alur):
  - benar 28, diterima tapi salah 1, ditolak 21;  rata-rata sekitar 5 detik per foto di CPU Colab.
  - Kode berbaris diputar terbaca baik; kode berhuruf BERTUMPUK vertikal tidak terbaca (ditolak, bukan salah catat).
  - Satu kesalahan terima yang diketahui: 'AKL636EE' adalah awalan dari 'AKL636EEA', jadi bacaan yang kehilangan
    huruf terakhir pada AKL636EEA dapat diterima sebagai AKL636EE.
"""

import time

from core.ocr import baca_paddleocr
from core.orientation import deskew, rotate_image
from core.preprocessing import adaptive_preprocess, apply_preprocessing
from core.validation import AMBANG_TERIMA_JARAK, koreksi_ke_kode_valid

MIN_CONF = 0.45   # batas bawah confidence OCR (nilai yang diuji)
MIN_LEN = 5       # panjang minimal bacaan (karakter)


def _baca_sekali(img, debug=False):
    """
    SATU kali pembacaan PaddleOCR pada satu crop. Mengembalikan bacaan APA ADANYA (setelah penyaringan karakter),
    belum dikenai batas panjang atau confidence, supaya bacaan yang ditolak pun tetap bisa ditampilkan ke operator.

    Returns:
        tuple: (teks, conf, sudut, nama_prep)
    """
    _nama_terbaik, _metrik_iqa, skor_semua = adaptive_preprocess(img, debug=debug)
    nama_prep = max(skor_semua, key=skor_semua.get)
    prep_fn = lambda im, _n=nama_prep: apply_preprocessing(im, _n)  # noqa: E731

    if img.shape[0] > img.shape[1]:
        im, sudut = rotate_image(img, 90), "90deg"
    else:
        im, sudut = deskew(img)[0], "deskew"

    teks, conf = baca_paddleocr(im, prep_fn)  # satu-satunya panggilan PaddleOCR
    return teks, conf, sudut, nama_prep


def _terapkan_batas(teks, conf, min_conf=MIN_CONF, min_len=MIN_LEN):
    """Bacaan terlalu pendek atau keyakinannya rendah dianggap TIDAK TERBACA (aturan yang diuji, tidak berubah)."""
    if not teks or len(teks) < min_len:
        return "[TIDAK TERBACA]", 0.0
    if conf < min_conf:
        return "[TIDAK TERBACA]", conf
    return teks, conf


def baca_cepat(img, min_conf=MIN_CONF, min_len=MIN_LEN, debug=False):
    """
    SATU kali pembacaan PaddleOCR pada satu crop, dengan batas panjang dan confidence diterapkan.

    Returns:
        tuple: (teks, conf, sudut, nama_prep)
    """
    teks, conf, sudut, nama_prep = _baca_sekali(img, debug=debug)
    teks, conf = _terapkan_batas(teks, conf, min_conf, min_len)
    return teks, conf, sudut, nama_prep


def _alasan_tolak(mentah, conf, jarak, ambang):
    """Kalimat alasan penolakan yang menyebut bacaannya, agar operator tahu apa yang sebenarnya terbaca."""
    if not mentah:
        return "mode cepat -> tidak ada teks yang terbaca -> cek manual"
    if len(mentah) < MIN_LEN:
        return f"mode cepat -> bacaan '{mentah}' terlalu pendek (minimal {MIN_LEN} karakter) -> cek manual"
    if conf < MIN_CONF:
        return f"mode cepat -> bacaan '{mentah}' ditolak karena keyakinan OCR rendah ({conf:.2f} < {MIN_CONF}) -> cek manual"
    detail = f", jarak terdekat {jarak:.1f} > batas {ambang:.1f}" if jarak is not None else ""
    return f"mode cepat -> bacaan '{mentah}' tidak cocok dengan daftar kode{detail} -> cek manual"


def baca_kode(crop, daftar_kode, ambang_terima=AMBANG_TERIMA_JARAK, debug=False):
    """
    Membaca kode dari satu crop dan memutuskan hasil akhirnya.

    Returns:
        dict: kode, confidence_ocr, status_baca ('VALID_TERBACA' | 'PERLU_VERIFIKASI'), alasan,
              waktu_ocr (detik), waktu_recovery (selalu 0.0, tidak ada jalur cadangan),
              teks_mentah (bacaan OCR apa adanya, juga saat ditolak; '' bila tidak ada teks),
              jarak_koreksi (jarak bacaan itu ke kode terdekat di Master Kode; None bila tidak ada teks).
    """
    t0 = time.perf_counter()
    teks_mentah, conf_mentah, sudut, nama_prep = _baca_sekali(crop, debug=debug)
    waktu_ocr = time.perf_counter() - t0

    teks, conf = _terapkan_batas(teks_mentah, conf_mentah)
    jarak_mentah = None
    if teks_mentah:
        _, jarak_mentah, _ = koreksi_ke_kode_valid(teks_mentah, daftar_kode, ambang_terima)

    teks_koreksi, jarak, yakin = koreksi_ke_kode_valid(teks, daftar_kode, ambang_terima)   # keputusan: tidak berubah
    if yakin:
        kode = teks_koreksi
        alasan = f"mode cepat -> bacaan cocok dengan daftar kode (jarak edit {jarak:.1f}, sudut {sudut}, prep {nama_prep})"
        status_baca = "VALID_TERBACA"
    else:
        kode = "[PERLU VERIFIKASI MANUAL]"
        alasan = _alasan_tolak(teks_mentah, conf_mentah, jarak_mentah, ambang_terima)
        status_baca = "PERLU_VERIFIKASI"

    return {
        "kode": kode,
        "confidence_ocr": conf,
        "status_baca": status_baca,
        "alasan": alasan,
        "waktu_ocr": round(waktu_ocr, 3),
        "waktu_recovery": 0.0,
        "teks_mentah": teks_mentah,
        "jarak_koreksi": jarak_mentah,
    }
