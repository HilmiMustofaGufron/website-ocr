"""blueprints/export/routes.py -- ekspor riwayat scan ke PDF dan Excel (filter sama dengan halaman History)."""

import logging

from flask import Blueprint, jsonify, request, send_file

from services import export

export_bp = Blueprint("export", __name__)
log = logging.getLogger(__name__)


def _filter_dari_query() -> dict:
    return {"tanggal": request.args.get("tanggal"), "kode": request.args.get("kode"), "status": request.args.get("status")}


@export_bp.route("/pdf", methods=["GET"])
def export_pdf():
    try:
        path = export.generate_pdf(_filter_dari_query())
    except Exception as exc:
        log.exception("Gagal membuat PDF: %s", exc)
        return jsonify({"error": "Gagal membuat PDF. Rinciannya ada di logs/app.log."}), 500
    return send_file(path, as_attachment=True, download_name="laporan_riwayat_scan.pdf")


@export_bp.route("/excel", methods=["GET"])
def export_excel():
    try:
        path = export.generate_excel(_filter_dari_query())
    except Exception as exc:
        log.exception("Gagal membuat Excel: %s", exc)
        return jsonify({"error": "Gagal membuat Excel. Rinciannya ada di logs/app.log."}), 500
    return send_file(path, as_attachment=True, download_name="laporan_riwayat_scan.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
