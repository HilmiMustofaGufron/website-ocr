"""blueprints/notifications/routes.py -- API notifikasi untuk ikon lonceng di bilah atas."""

from flask import Blueprint, jsonify

from services import notifications

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/", methods=["GET"])
def daftar():
    return jsonify(notifications.daftar_terbaru())


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
def tandai_dibaca(notif_id):
    if not notifications.tandai_dibaca(notif_id):
        return jsonify({"error": "Notifikasi tidak ditemukan."}), 404
    return jsonify({"status": "ok", "id": notif_id})


@notifications_bp.route("/read-all", methods=["POST"])
def tandai_semua():
    return jsonify({"status": "ok", "jumlah": notifications.tandai_semua_dibaca()})
