"""blueprints/history/routes.py -- melihat, mencari, dan menghapus riwayat hasil scan."""

import os

from flask import Blueprint, current_app, jsonify, render_template, request

from services import database

history_bp = Blueprint("history", __name__)


def _hapus_berkas_gambar(riwayat: dict) -> None:
    """Menghapus gambar milik satu riwayat, HANYA bila berada di folder unggahan (mencegah penghapusan berkas lain)."""
    folder = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    for kunci in ("path_gambar", "path_crop", "path_deteksi"):
        p = riwayat.get(kunci)
        if not p:
            continue
        lengkap = os.path.realpath(os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(p)))
        if os.path.commonpath([folder, lengkap]) == folder and os.path.isfile(lengkap):
            try:
                os.remove(lengkap)
            except OSError:
                pass


@history_bp.route("/", methods=["GET"])
def history_page():
    return render_template("history/index.html", riwayat=database.get_scan_history(limit=50))


@history_bp.route("/search", methods=["GET"])
def history_search():
    filters = {"tanggal": request.args.get("tanggal"), "kode": request.args.get("kode"), "status": request.args.get("status")}
    return jsonify(database.search_scan_history(filters))


@history_bp.route("/<int:history_id>", methods=["DELETE"])
def history_delete(history_id):
    riwayat = database.get_scan_by_id(history_id)
    if riwayat is None or not database.delete_scan_history(history_id):
        return jsonify({"error": "Riwayat tidak ditemukan."}), 404
    _hapus_berkas_gambar(riwayat)
    return jsonify({"status": "deleted", "id": history_id})
