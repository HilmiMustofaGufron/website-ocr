"""
utils/security.py
=================
Perlindungan CSRF dan kewajiban login, dipasang sekali di app factory (berlaku untuk semua route).

CSRF: setiap sesi punya token acak. Setiap permintaan yang mengubah data (POST, PUT, PATCH, DELETE) wajib membawa
token itu, lewat header X-CSRF-Token (dipasang otomatis oleh static/js/main.js) atau field formulir csrf_token.
Tanpa token yang benar, server menolak (403). Ini mencegah situs lain menyuruh browser operator yang sedang login
mengubah data tanpa sepengetahuannya.
"""

import hmac
import os
import secrets
from urllib.parse import urlparse

from flask import abort, jsonify, redirect, request, session, url_for

METODE_UBAH = {"POST", "PUT", "PATCH", "DELETE"}
ENDPOINT_BEBAS_LOGIN = {"auth.login", "static"}
# Halaman HTML: bila belum login, diarahkan ke halaman login. Selain itu (API) dijawab 401 JSON.
HALAMAN_HTML = {
    "dashboard.index", "dashboard.dashboard", "monitoring.monitoring_page", "history.history_page",
    "master_kode.master_kode_page", "settings.settings_page",
}


# Penanda "umur proses": dibuat BARU setiap aplikasi dijalankan, dicatat di sesi saat login, dan diperiksa pada setiap
# permintaan. Sesi yang dibuat oleh proses LAMA (sebelum aplikasi dijalankan ulang) otomatis dianggap tidak berlaku,
# sehingga setelah restart pengguna harus masuk lagi. Kunci rahasia (SECRET_KEY) tetap sama, jadi tidak ada yang
# bergantung pada perubahan kunci. Matikan perilaku ini dengan SESI_BERAKHIR_SAAT_RESTART=0 di berkas .env.
ID_SERVER = secrets.token_hex(16)


def sesi_berakhir_saat_restart() -> bool:
    return os.environ.get("SESI_BERAKHIR_SAAT_RESTART", "1") != "0"


def tandai_sesi_login() -> None:
    """Dipanggil tepat setelah login berhasil: mencatat bahwa sesi ini milik proses yang sedang berjalan."""
    session["id_server"] = ID_SERVER


def sesi_valid() -> bool:
    """True bila pengguna sudah login DAN sesinya dibuat oleh proses yang sedang berjalan."""
    if not session.get("user_id"):
        return False
    if sesi_berakhir_saat_restart() and session.get("id_server") != ID_SERVER:
        return False
    return True


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _tolak(kode: int, pesan: str):
    if request.endpoint in HALAMAN_HTML or request.endpoint == "auth.login":
        abort(kode, description=pesan)
    return jsonify({"error": pesan}), kode


def periksa_permintaan():
    """before_request: wajib login, lalu cek CSRF untuk permintaan yang mengubah data."""
    endpoint = request.endpoint
    if endpoint is None:          # URL tidak dikenal: biar penangan 404 yang menjawab
        return None

    if endpoint not in ENDPOINT_BEBAS_LOGIN and not sesi_valid():
        basi = bool(session.get("user_id"))      # ada sesi lama yang tidak berlaku lagi (mis. aplikasi dijalankan ulang)
        if basi:
            session.clear()
        if endpoint in HALAMAN_HTML:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?"), sesi="berakhir" if basi else None))
        return jsonify({"error": "Belum login atau sesi sudah berakhir."}), 401

    if request.method in METODE_UBAH and endpoint != "static":
        dikirim = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
        asli = session.get("csrf_token", "")
        if not asli or not hmac.compare_digest(str(dikirim), str(asli)):
            return _tolak(403, "Token keamanan (CSRF) tidak valid. Muat ulang halaman lalu coba lagi.")
    return None


def tambah_header_keamanan(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    return response


def tujuan_aman(tujuan: str, bawaan: str) -> str:
    """Hanya izinkan pengalihan ke path di situs ini (mencegah open redirect lewat parameter ?next=)."""
    if not tujuan:
        return bawaan
    u = urlparse(tujuan)
    if u.scheme or u.netloc or not tujuan.startswith("/") or tujuan.startswith("//") or "\\" in tujuan:
        return bawaan
    return tujuan
