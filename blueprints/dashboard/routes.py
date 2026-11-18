"""blueprints/dashboard/routes.py -- halaman utama (Dashboard)."""

import os

from flask import Blueprint, current_app, render_template

from services import database

dashboard_bp = Blueprint("dashboard", __name__)


def _peringatan_sistem() -> list:
    """Hal yang membuat pindai tidak bisa berjalan benar; ditampilkan di Dashboard supaya operator langsung tahu."""
    daftar = []
    if not os.path.isfile(current_app.config["MODEL_YOLO_PATH"]):
        daftar.append("Model YOLO belum ada. Letakkan berkas best_lokasi_new.pt di folder models_ai/, "
                      "lalu jalankan ulang aplikasi. Selama itu pindai tidak dapat berjalan.")
    if not database.get_daftar_kode_valid():
        daftar.append("Master Kode masih kosong. Tanpa daftar kode, semua hasil pindai akan ditolak. "
                      "Tambahkan kode lewat halaman Master Kode.")
    return daftar


@dashboard_bp.route("/", methods=["GET"])
def index():
    return render_template("dashboard/index.html", ringkasan=database.get_dashboard_summary(), peringatan=_peringatan_sistem())


@dashboard_bp.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard/index.html", ringkasan=database.get_dashboard_summary(), peringatan=_peringatan_sistem())
