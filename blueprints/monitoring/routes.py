"""blueprints/monitoring/routes.py -- halaman monitoring real-time (kamera langsung dan hasil scan terakhir)."""

from flask import Blueprint, render_template

from services import database

monitoring_bp = Blueprint("monitoring", __name__)


@monitoring_bp.route("/", methods=["GET"])
def monitoring_page():
    """`pengaturan` diteruskan agar JavaScript tahu interval_scan dan auto_scan tanpa permintaan tambahan."""
    return render_template("monitoring/index.html", pengaturan=database.get_settings())
