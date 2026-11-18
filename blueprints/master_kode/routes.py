"""blueprints/master_kode/routes.py -- tambah, ubah, hapus, dan impor daftar kode produk valid."""

from flask import Blueprint, jsonify, render_template, request

from services import database, notifications
from services.database import DataTidakValid

master_kode_bp = Blueprint("master_kode", __name__)


@master_kode_bp.route("/", methods=["GET"])
def master_kode_page():
    return render_template("master_kode/index.html", daftar_kode=database.get_all_master_kode())


@master_kode_bp.route("/", methods=["POST"])
def master_kode_create():
    data = request.get_json(silent=True) or request.form
    try:
        hasil = database.create_master_kode({"kode": data.get("kode"), "keterangan": data.get("keterangan")})
    except DataTidakValid as exc:
        # kode kembar -> 409, selain itu (format salah) -> 400
        return jsonify({"error": str(exc)}), (409 if "sudah" in str(exc) else 400)
    return jsonify(hasil), 201


@master_kode_bp.route("/<int:kode_id>", methods=["PUT"])
def master_kode_update(kode_id):
    data = request.get_json(silent=True) or request.form
    try:
        hasil = database.update_master_kode(kode_id, {"kode": data.get("kode"), "keterangan": data.get("keterangan")})
    except DataTidakValid as exc:
        return jsonify({"error": str(exc)}), (409 if "sudah" in str(exc) else 400)
    if hasil is None:
        return jsonify({"error": "Kode tidak ditemukan."}), 404
    return jsonify(hasil)


@master_kode_bp.route("/<int:kode_id>", methods=["DELETE"])
def master_kode_delete(kode_id):
    if not database.delete_master_kode(kode_id):
        return jsonify({"error": "Kode tidak ditemukan."}), 404
    return jsonify({"status": "deleted", "id": kode_id})


@master_kode_bp.route("/import", methods=["POST"])
def master_kode_import():
    """Impor dari Excel (.xlsx, field 'file'). Kode kembar dilewati dan tidak menimpa keterangan yang ada."""
    berkas = request.files.get("file")
    if berkas is None or not berkas.filename:
        return jsonify({"error": "Tidak ada file yang diunggah (field 'file')."}), 400
    if not berkas.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"error": "File harus berformat Excel (.xlsx)."}), 400
    try:
        ringkasan = database.import_master_kode_excel(berkas)
    except DataTidakValid as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Gagal membaca file Excel: {exc}"}), 400
    notifications.create(
        "import_selesai",
        f"Import selesai: {ringkasan['berhasil']} kode ditambahkan, {ringkasan['dilewati']} dilewati, {ringkasan['gagal']} gagal.",
    )
    return jsonify(ringkasan)
