"""
blueprints/auth/routes.py
=========================
Login, logout, dan ganti akun. Sesi memakai cookie bertanda tangan milik Flask (cukup untuk sistem satu server).
"""

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services import auth
from utils.security import csrf_token, sesi_valid, tandai_sesi_login, tujuan_aman

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if sesi_valid():
            return redirect(url_for("dashboard.dashboard"))
        if session.get("user_id"):
            session.clear()   # sesi lama dari proses sebelumnya: bersihkan supaya tidak berputar-putar
        csrf_token()  # pastikan token sesi ada sebelum formulir ditampilkan
        info = ("Sesi sudah berakhir. Silakan masuk lagi."
                if request.args.get("sesi") == "berakhir" else None)
        return render_template("auth/login.html", info=info)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    terkunci, detik = auth.cek_status_kunci(username)
    if terkunci:
        menit = max(1, (detik + 59) // 60)
        return render_template("auth/login.html", error=f"Terlalu banyak percobaan gagal. Coba lagi dalam {menit} menit."), 429

    user = auth.verifikasi_login(username, password)
    if user is None:
        auth.catat_percobaan_gagal(username)
        return render_template("auth/login.html", error="Username atau password salah."), 401

    auth.reset_percobaan_login(username)
    token_lama = session.get("csrf_token")
    session.clear()                      # sesi baru setelah login (mencegah session fixation)
    if token_lama:
        session["csrf_token"] = token_lama
    session.permanent = True
    tandai_sesi_login()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["nama_tampilan"] = user["nama_tampilan"] or user["username"]
    return redirect(tujuan_aman(request.args.get("next"), url_for("dashboard.dashboard")))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/account", methods=["POST"])
def update_account():
    """
    Mengganti username dan/atau password akun yang sedang login. WAJIB memasukkan password SAAT INI sebagai
    verifikasi (supaya orang lain tidak bisa iseng mengubah kredensial bila sesi browser ditinggal terbuka).
    """
    user_id = session.get("user_id")
    password_sekarang = request.form.get("password_sekarang", "")
    username_baru = request.form.get("username_baru", "").strip()
    password_baru = request.form.get("password_baru", "")
    konfirmasi = request.form.get("konfirmasi_password", "")

    if not auth.cek_password_pengguna(user_id, password_sekarang):
        return jsonify({"error": "Password saat ini salah."}), 400
    if password_baru:
        if password_baru != konfirmasi:
            return jsonify({"error": "Konfirmasi password baru tidak cocok."}), 400
        if len(password_baru) < auth.PANJANG_MIN_PASSWORD:
            return jsonify({"error": f"Password baru minimal {auth.PANJANG_MIN_PASSWORD} karakter."}), 400
    if username_baru and username_baru != session.get("username"):
        if not auth.ganti_username(user_id, username_baru):
            return jsonify({"error": f"Username '{username_baru}' sudah dipakai."}), 409
        session["username"] = username_baru
        session["nama_tampilan"] = username_baru
    if password_baru:
        auth.ganti_password(user_id, password_baru)
    return jsonify({"status": "ok", "username": session.get("username")})
