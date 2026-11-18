"""
config.py
=========
Konfigurasi terpusat. Nilai bawaan sudah sesuai hasil pengujian; semuanya bisa diubah lewat environment
variable (atau berkas .env) TANPA mengubah kode.

Semua path bersifat absolut (berbasis BASE_DIR) supaya aplikasi berjalan benar dari folder mana pun.
"""

import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


def _muat_dotenv():
    """Membaca berkas .env sederhana (KUNCI=nilai) bila ada, tanpa menimpa environment variable yang sudah di-set."""
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for baris in f:
            baris = baris.strip()
            if not baris or baris.startswith("#") or "=" not in baris:
                continue
            kunci, nilai = baris.split("=", 1)
            os.environ.setdefault(kunci.strip(), nilai.strip().strip('"').strip("'"))


_muat_dotenv()


def _secret_key() -> str:
    """SECRET_KEY dari environment; kalau tidak ada, dibuat sekali lalu disimpan di instance/secret_key
    supaya sesi login tetap berlaku setelah aplikasi di-restart."""
    dari_env = os.environ.get("SECRET_KEY")
    if dari_env:
        return dari_env
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    kunci = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(kunci)
    return kunci


class BaseConfig:
    # --- Flask ---
    SECRET_KEY = _secret_key()
    JSON_SORT_KEYS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB: batas ukuran foto/berkas unggahan

    # --- Database & folder ---
    DATABASE_PATH = os.path.join(INSTANCE_DIR, "warehouse.db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    EXPORT_FOLDER = os.path.join(BASE_DIR, "static", "exports")
    LOG_FOLDER = os.path.join(BASE_DIR, "logs")

    # --- Model AI ---
    MODEL_YOLO_PATH = os.environ.get("MODEL_YOLO_PATH", os.path.join(BASE_DIR, "models_ai", "best_lokasi_new.pt"))

    # --- Pembacaan kode (nilai yang diuji pada 50 foto) ---
    AMBANG_TERIMA_JARAK = float(os.environ.get("AMBANG_TERIMA_JARAK", "2.0"))
    MAX_DIMENSI_PROSES = int(os.environ.get("MAX_DIMENSI_PROSES", "1600"))

    # --- Bawaan pengaturan operator (nilai aktif disimpan di tabel settings) ---
    DEFAULT_YOLO_THRESHOLD = 0.4
    DEFAULT_SCAN_INTERVAL_MS = 500
    DEFAULT_AUTO_SCAN = True

    # --- Akun awal (dibuat hanya bila tabel users masih kosong) ---
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # kosong -> dibuat acak dan dicetak sekali di terminal

    # --- Keamanan login ---
    MAKS_PERCOBAAN_GAGAL = 5
    DURASI_KUNCI = timedelta(minutes=5)


class DevelopmentConfig(BaseConfig):
    DEBUG = False  # sengaja mati: debugger Werkzeug yang terbuka di jaringan berbahaya; nyalakan lewat FLASK_DEBUG=1


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
