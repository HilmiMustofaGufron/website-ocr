"""blueprints/camera/routes.py -- kontrol kamera (mulai, henti, frame, status)."""

import cv2
from flask import Blueprint, Response, current_app, jsonify, request

from services import camera, database, notifications

camera_bp = Blueprint("camera", __name__)


def _buat_callback_terputus(app):
    """Callback yang dipanggil thread kamera saat koneksi terputus: membuat notifikasi di dalam app context."""
    def _terputus():
        with app.app_context():
            notifications.create("kamera_terputus", "Koneksi kamera terputus. Periksa kabel atau aplikasi kamera, lalu mulai lagi.")
    return _terputus


@camera_bp.route("/start", methods=["POST"])
def start_camera():
    """
    Memulai streaming kamera. Body JSON opsional: {"source": 0} (indeks perangkat atau URL). Bila tidak dikirim,
    dipakai `kamera_aktif` dari settings; bila itu kosong juga, indeks 0.
    """
    data = request.get_json(silent=True) or {}
    pengaturan = database.get_settings()
    source = data.get("source", pengaturan.kamera_aktif or 0)
    if isinstance(source, str) and source.strip().isdigit():
        source = int(source.strip())
    if isinstance(source, float):
        source = int(source)
    if not isinstance(source, (int, str)) or isinstance(source, bool):
        return jsonify({"status": "error", "pesan_error": "Sumber kamera tidak valid."}), 400

    if not camera.start_stream(source, on_terputus=_buat_callback_terputus(current_app._get_current_object())):
        return jsonify({"status": "error", **camera.get_camera_status()}), 500
    database.update_settings({"kamera_aktif": str(source)})
    return jsonify({"status": "started", **camera.get_camera_status()})


@camera_bp.route("/stop", methods=["POST"])
def stop_camera():
    camera.stop_stream()
    from services import scan_state
    scan_state.state_machine_aktif.reset()
    return jsonify({"status": "stopped"})


@camera_bp.route("/frame", methods=["GET"])
def get_frame():
    """Frame terbaru sebagai JPEG tunggal (dipakai <img src="/camera/frame"> dengan penyegaran berkala)."""
    frame = camera.get_latest_frame()
    if frame is None:
        return jsonify({"error": "Belum ada frame: kamera belum aktif atau belum sempat membaca frame."}), 503
    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        return jsonify({"error": "Gagal mengubah frame menjadi JPEG."}), 500
    return Response(buffer.tobytes(), mimetype="image/jpeg")


@camera_bp.route("/status", methods=["GET"])
def camera_status():
    return jsonify(camera.get_camera_status())
