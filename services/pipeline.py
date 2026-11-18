"""
services/pipeline.py
====================
Titik masuk TUNGGAL alur pindai: YOLO (lokasi kode) -> crop -> pembaca mode cepat -> validasi -> notifikasi ->
(opsional) simpan ke database. Route (scan, kamera) hanya memanggil scan_produk() di sini.

Mengikat inti pembaca (core/, murni algoritma) dengan aplikasi: pengaturan operator, daftar kode dari database,
penyimpanan gambar, notifikasi, dan riwayat.
"""

import os
import time
import uuid

import cv2
from flask import current_app

from core import detector, reader
from core.validation import status_kode
from services import database, notifications


def _simpan_gambar(frame, awalan: str, uid: str) -> str:
    """Menyimpan gambar ke folder unggahan; mengembalikan path relatif (untuk disimpan ke database)."""
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    nama = f"{uid}_{awalan}.jpg"
    cv2.imwrite(os.path.join(folder, nama), frame)
    return "static/uploads/" + nama


def ada_objek(frame, threshold_yolo: float) -> bool:
    """YOLO saja (murah): ada objek di frame atau tidak. Dipakai mesin status scan langsung."""
    frame = detector.perkecil_bila_besar(frame, current_app.config["MAX_DIMENSI_PROSES"])
    return len(detector.detect_semua(frame, current_app.config["MODEL_YOLO_PATH"], threshold_yolo)) > 0


def scan_produk(frame, simpan_ke_db: bool = True, simpan_gambar: bool = True) -> dict:
    """
    Satu siklus penuh untuk satu frame.

    Returns:
        dict: kode, confidence_yolo, confidence_ocr, processing_time, status, waktu_yolo, waktu_ocr,
              waktu_recovery, alasan_keputusan, path_gambar, path_crop, path_deteksi
    Raises:
        core.detector.ModelTidakDitemukan: bila berkas model YOLO tidak ada.
    """
    cfg = current_app.config
    uid = uuid.uuid4().hex[:8]
    t_mulai = time.perf_counter()
    frame = detector.perkecil_bila_besar(frame, cfg["MAX_DIMENSI_PROSES"])
    pengaturan = database.get_settings()

    t0 = time.perf_counter()
    deteksi = detector.detect_semua(frame, cfg["MODEL_YOLO_PATH"], conf_threshold=pengaturan.threshold_yolo)
    waktu_yolo = time.perf_counter() - t0

    path_gambar = _simpan_gambar(frame, "asli", uid) if simpan_gambar else None
    path_deteksi = (
        _simpan_gambar(detector.gambar_kotak_deteksi(frame, deteksi), "deteksi", uid)
        if (simpan_gambar and deteksi) else None
    )

    if not deteksi:
        return {
            "kode": None, "confidence_yolo": 0.0, "confidence_ocr": 0.0,
            "processing_time": round(time.perf_counter() - t_mulai, 3),
            "status": "NOT_FOUND",
            "waktu_yolo": round(waktu_yolo, 3), "waktu_ocr": 0.0, "waktu_recovery": 0.0,
            "alasan_keputusan": "YOLO tidak mendeteksi area teks pada gambar.",
            "path_gambar": path_gambar, "path_crop": None, "path_deteksi": path_deteksi,
            "teks_terbaca": None, "jarak_koreksi": None,
        }

    crop, _bbox = detector.crop_gabungan(frame, deteksi)
    path_crop = _simpan_gambar(crop, "crop", uid) if (simpan_gambar and crop is not None) else None

    daftar_kode = database.get_daftar_kode_valid()
    ambang = cfg["AMBANG_TERIMA_JARAK"]
    hasil_ocr = reader.baca_kode(crop, daftar_kode, ambang_terima=ambang)
    status_akhir = status_kode(hasil_ocr["kode"], daftar_kode, ambang)
    kode_akhir = hasil_ocr["kode"] if status_akhir != "NOT_FOUND" else None

    # Notifikasi hanya untuk "objek terdeteksi tetapi kode tidak dikenali/tidak terbaca" (bukan frame kosong).
    # Pesannya menyebut bacaan OCR, supaya operator tahu apa yang sebenarnya terbaca.
    if status_akhir != "VALID":
        mentah = hasil_ocr["teks_mentah"]
        if mentah:
            pesan = f"Objek terdeteksi, tetapi bacaan '{mentah}' tidak cocok dengan Master Kode (perlu verifikasi manual)."
        else:
            pesan = "Objek terdeteksi, tetapi tidak ada teks yang terbaca (perlu verifikasi manual)."
        notifications.create("scan_tidak_dikenali", pesan)

    hasil = {
        "kode": kode_akhir,
        "confidence_yolo": deteksi[0]["confidence"],
        "confidence_ocr": hasil_ocr["confidence_ocr"],
        "processing_time": round(time.perf_counter() - t_mulai, 3),
        "status": status_akhir,
        "waktu_yolo": round(waktu_yolo, 3),
        "waktu_ocr": hasil_ocr["waktu_ocr"],
        "waktu_recovery": hasil_ocr["waktu_recovery"],
        "alasan_keputusan": hasil_ocr["alasan"],
        "path_gambar": path_gambar,
        "path_crop": path_crop,
        "path_deteksi": path_deteksi,
        "teks_terbaca": hasil_ocr["teks_mentah"],
        "jarak_koreksi": hasil_ocr["jarak_koreksi"],
    }
    if simpan_ke_db:
        database.save_scan_result(hasil)
    return hasil
