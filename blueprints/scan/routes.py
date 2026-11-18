"""blueprints/scan/routes.py -- memicu alur pindai: unggah foto, pindai langsung dari kamera, dan status."""

import logging

import cv2
import numpy as np
from flask import Blueprint, current_app, jsonify, request

from core.detector import ModelTidakDitemukan
from services import camera, database, pipeline, scan_state

scan_bp = Blueprint("scan", __name__)
log = logging.getLogger(__name__)

EKSTENSI_GAMBAR = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _galat_pindai(exc):
    """Menerjemahkan kegagalan alur pindai menjadi jawaban JSON yang jelas bagi operator."""
    if isinstance(exc, ModelTidakDitemukan):
        return jsonify({"error": str(exc)}), 503
    log.exception("Pindai gagal: %s", exc)
    return jsonify({"error": "Pindai gagal karena kesalahan di server. Rinciannya ada di logs/app.log."}), 500


@scan_bp.route("/image", methods=["POST"])
def scan_image():
    """Satu kali pindai pada foto yang diunggah (field 'file'). Berguna untuk uji tanpa kamera."""
    berkas = request.files.get("file")
    if berkas is None or not berkas.filename:
        return jsonify({"error": "Tidak ada file yang diunggah (field 'file')."}), 400
    nama = berkas.filename.lower()
    if not any(nama.endswith(e) for e in EKSTENSI_GAMBAR):
        return jsonify({"error": "Format file harus gambar (jpg, jpeg, png, bmp, atau webp)."}), 400

    frame = cv2.imdecode(np.frombuffer(berkas.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "Gagal membaca file sebagai gambar."}), 400
    try:
        return jsonify(pipeline.scan_produk(frame, simpan_ke_db=True))
    except Exception as exc:
        return _galat_pindai(exc)


@scan_bp.route("/live", methods=["POST"])
def scan_live():
    """
    Memproses SATU frame terbaru dari kamera lewat mesin status. Dipanggil berulang oleh JavaScript di halaman
    Monitoring setiap `interval_scan` milidetik selama auto scan aktif. Mesin status yang memutuskan kapan
    pembacaan kode benar-benar dijalankan.
    """
    pengaturan = database.get_settings()
    if not pengaturan.auto_scan:
        return jsonify({"status": "auto_scan_off"}), 200
    frame = camera.get_latest_frame()
    if frame is None:
        return jsonify({"error": "Belum ada frame dari kamera."}), 503
    try:
        hasil = scan_state.state_machine_aktif.process_frame(
            frame,
            ada_objek_fn=lambda f: pipeline.ada_objek(f, pengaturan.threshold_yolo),
            scan_fn=pipeline.scan_produk,
        )
    except Exception as exc:
        return _galat_pindai(exc)
    return jsonify(hasil)


@scan_bp.route("/status", methods=["GET"])
def scan_status():
    """Status mesin scan dan hasil scan terakhir (untuk Monitoring)."""
    return jsonify(scan_state.state_machine_aktif.status())
