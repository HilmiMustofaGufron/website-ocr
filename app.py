"""
app.py
======
Pabrik aplikasi Flask. Jalankan dengan:  python app.py   (atau jalankan.bat di Windows)

Yang dilakukan saat start: siapkan folder, logging, database, keamanan (login + CSRF), semua blueprint, dan
akun awal bila belum ada pengguna.
"""

import os

from flask import Flask, jsonify, render_template, request, session

from config import config_by_name
from database.db import init_db
from utils.logger import setup_logger
from utils.security import csrf_token, periksa_permintaan, tambah_header_keamanan


def create_app(config_name: str = None, overrides: dict = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_by_name[config_name])
    if overrides:
        app.config.update(overrides)

    _siapkan_folder(app)
    setup_logger(app)
    init_db(app)

    _pasang_keamanan(app)
    _daftarkan_blueprint(app)
    _pasang_penangan_galat(app)
    _siapkan_akun_awal(app)

    if not os.path.isfile(app.config["MODEL_YOLO_PATH"]):
        app.logger.warning("Model YOLO belum ada di %s. Pindai tidak akan berjalan sebelum berkas diletakkan di sana.",
                           app.config["MODEL_YOLO_PATH"])
    return app


def _siapkan_folder(app: Flask) -> None:
    for folder in (os.path.dirname(app.config["DATABASE_PATH"]), app.config["UPLOAD_FOLDER"],
                   app.config["EXPORT_FOLDER"], app.config["LOG_FOLDER"]):
        os.makedirs(folder, exist_ok=True)


def _pasang_keamanan(app: Flask) -> None:
    app.before_request(periksa_permintaan)
    app.after_request(tambah_header_keamanan)

    @app.context_processor
    def _konteks_umum():
        return {"csrf_token": csrf_token(), "pengguna_nama": session.get("nama_tampilan") or session.get("username")}


def _daftarkan_blueprint(app: Flask) -> None:
    from blueprints.auth.routes import auth_bp
    from blueprints.camera.routes import camera_bp
    from blueprints.dashboard.routes import dashboard_bp
    from blueprints.export.routes import export_bp
    from blueprints.history.routes import history_bp
    from blueprints.master_kode.routes import master_kode_bp
    from blueprints.monitoring.routes import monitoring_bp
    from blueprints.notifications.routes import notifications_bp
    from blueprints.scan.routes import scan_bp
    from blueprints.settings.routes import settings_bp

    app.register_blueprint(auth_bp)                                          # /login, /logout, /account
    app.register_blueprint(dashboard_bp)                                     # /, /dashboard
    app.register_blueprint(monitoring_bp, url_prefix="/monitoring")
    app.register_blueprint(camera_bp, url_prefix="/camera")
    app.register_blueprint(scan_bp, url_prefix="/scan")
    app.register_blueprint(history_bp, url_prefix="/history")
    app.register_blueprint(master_kode_bp, url_prefix="/master-kode")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(export_bp, url_prefix="/export")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")


def _pasang_penangan_galat(app: Flask) -> None:
    PESAN = {
        403: "Akses ditolak.", 404: "Halaman tidak ditemukan.", 405: "Metode tidak diizinkan.",
        413: "Berkas terlalu besar (maksimal 16 MB).", 429: "Terlalu banyak permintaan.",
        500: "Terjadi kesalahan di server.",
    }

    def _tangani(kode):
        def penangan(galat):
            deskripsi = getattr(galat, "description", None) if kode in (403,) else None
            pesan = deskripsi or PESAN.get(kode, "Terjadi kesalahan.")
            if request.accept_mimetypes.best == "text/html" and request.method == "GET":
                return render_template("error.html", kode=kode, pesan=pesan), kode
            return jsonify({"error": pesan}), kode
        return penangan

    for kode in (403, 404, 405, 413, 500):
        app.register_error_handler(kode, _tangani(kode))


def _siapkan_akun_awal(app: Flask) -> None:
    """Membuat akun awal bila tabel users kosong. Kata sandi acak dicetak SEKALI di terminal dan disimpan di instance/."""
    from services import auth

    with app.app_context():
        hasil = auth.pastikan_akun_awal()
    if hasil is None:
        return
    username, password = hasil
    if password is None:
        app.logger.info("Akun awal '%s' dibuat dari ADMIN_PASSWORD.", username)
        print(f"\n[AKUN AWAL] Username: {username} | Password: sesuai ADMIN_PASSWORD di .env\n")
        return
    path = os.path.join(os.path.dirname(app.config["DATABASE_PATH"]), "kredensial_awal.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Username: {username}\nPassword: {password}\n(Ganti password setelah login lewat halaman Settings, lalu hapus berkas ini.)\n")
    app.logger.info("Akun awal '%s' dibuat dengan password acak (disimpan di %s).", username, path)
    print("\n" + "=" * 60)
    print("AKUN AWAL DIBUAT (tampil sekali ini saja)")
    print(f"  Username : {username}")
    print(f"  Password : {password}")
    print(f"  Disimpan : {path}")
    print("Ganti password setelah login (halaman Settings), lalu hapus berkas itu.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    flask_app = create_app()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    print(f"\nBuka di browser: http://127.0.0.1:{port}   (dari perangkat lain di jaringan yang sama: http://<IP-laptop>:{port})\n")
    flask_app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1", threaded=True)
