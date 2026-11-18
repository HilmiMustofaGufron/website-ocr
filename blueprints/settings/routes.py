"""blueprints/settings/routes.py -- pengaturan operator (ambang YOLO, auto scan, interval, kamera)."""

from flask import Blueprint, jsonify, render_template, request

from services import database

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/", methods=["GET"])
def settings_page():
    return render_template("settings/index.html", settings=database.get_settings())


@settings_bp.route("/", methods=["POST"])
def settings_update():
    """Menyimpan pengaturan. Nilai divalidasi di sini sebelum diteruskan ke database."""
    data = request.get_json(silent=True) or request.form.to_dict()
    bersih = {}

    if data.get("threshold_yolo") not in (None, ""):
        try:
            nilai = float(data["threshold_yolo"])
        except (TypeError, ValueError):
            return jsonify({"error": "threshold_yolo harus berupa angka."}), 400
        if not (0.0 <= nilai <= 1.0):
            return jsonify({"error": "threshold_yolo harus di antara 0 dan 1."}), 400
        bersih["threshold_yolo"] = nilai

    if data.get("interval_scan") not in (None, ""):
        try:
            interval = int(data["interval_scan"])
        except (TypeError, ValueError):
            return jsonify({"error": "interval_scan harus berupa bilangan bulat (ms)."}), 400
        if not (100 <= interval <= 60000):
            return jsonify({"error": "interval_scan harus antara 100 dan 60000 ms."}), 400
        bersih["interval_scan"] = interval

    if "auto_scan" in data:
        bersih["auto_scan"] = str(data["auto_scan"]).lower() in ("1", "true", "on", "yes")

    if "kamera_aktif" in data:
        kamera = str(data["kamera_aktif"] or "").strip()
        if len(kamera) > 200:
            return jsonify({"error": "kamera_aktif terlalu panjang."}), 400
        bersih["kamera_aktif"] = kamera or None

    return jsonify(database.update_settings(bersih).to_dict())
