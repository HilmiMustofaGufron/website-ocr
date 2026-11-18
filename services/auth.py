"""
services/auth.py
================
Autentikasi: verifikasi login, pengambilan data pengguna, dan pembatasan percobaan login.
Kata sandi TIDAK PERNAH disimpan atau dibandingkan sebagai teks biasa, selalu lewat hash (werkzeug.security).

Pembatasan percobaan (mencegah menebak kata sandi tanpa batas): setelah MAKS_PERCOBAAN_GAGAL kali gagal berturut-turut,
username itu dikunci selama DURASI_KUNCI. Disimpan di memori (direset saat server di-restart), cukup untuk sistem
satu server ini. Kunci dihitung per username TANPA membedakan huruf besar/kecil, supaya tidak mudah dilewati.
"""

import secrets
import string
import threading
from datetime import datetime

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_connection

PANJANG_MIN_PASSWORD = 6

_percobaan = {}   # {username_kecil: {"gagal": int, "terkunci_hingga": datetime | None}}
_lock = threading.Lock()


def _kunci(username: str) -> str:
    return (username or "").strip().lower()


def cek_status_kunci(username: str):
    """Returns (terkunci: bool, detik_tersisa: int)."""
    k = _kunci(username)
    with _lock:
        data = _percobaan.get(k)
        if not data or not data.get("terkunci_hingga"):
            return False, 0
        sisa = (data["terkunci_hingga"] - datetime.now()).total_seconds()
        if sisa <= 0:
            _percobaan.pop(k, None)   # masa kunci habis: reset otomatis
            return False, 0
        return True, int(sisa)


def catat_percobaan_gagal(username: str) -> None:
    k = _kunci(username)
    with _lock:
        data = _percobaan.setdefault(k, {"gagal": 0, "terkunci_hingga": None})
        data["gagal"] += 1
        if data["gagal"] >= current_app.config["MAKS_PERCOBAAN_GAGAL"]:
            data["terkunci_hingga"] = datetime.now() + current_app.config["DURASI_KUNCI"]


def reset_percobaan_login(username: str) -> None:
    with _lock:
        _percobaan.pop(_kunci(username), None)


def reset_semua_percobaan() -> None:
    """Hanya untuk pengujian."""
    with _lock:
        _percobaan.clear()


def verifikasi_login(username: str, password: str):
    """Returns dict pengguna (tanpa hash) bila benar, None bila username tidak ada atau kata sandi salah."""
    row = get_connection().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        # Tetap menghitung hash palsu supaya waktu respons tidak membocorkan apakah username ada.
        check_password_hash("pbkdf2:sha256:600000$x$" + "0" * 64, password)
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return {"id": row["id"], "username": row["username"], "nama_tampilan": row["nama_tampilan"]}


def get_user_by_id(user_id: int):
    row = get_connection().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"], "nama_tampilan": row["nama_tampilan"]}


def jumlah_pengguna() -> int:
    return get_connection().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def buat_pengguna(username: str, password: str, nama_tampilan: str = None) -> int:
    username = (username or "").strip()
    if not username:
        raise ValueError("Username tidak boleh kosong.")
    if len(password or "") < PANJANG_MIN_PASSWORD:
        raise ValueError(f"Password minimal {PANJANG_MIN_PASSWORD} karakter.")
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, nama_tampilan) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), nama_tampilan or username),
    )
    conn.commit()
    return cur.lastrowid


def atur_password_pengguna(username: str, password_baru: str) -> bool:
    """Mengatur ulang kata sandi berdasarkan username (dipakai buat_pengguna.py bila lupa kata sandi)."""
    if len(password_baru or "") < PANJANG_MIN_PASSWORD:
        raise ValueError(f"Password minimal {PANJANG_MIN_PASSWORD} karakter.")
    conn = get_connection()
    cur = conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                       (generate_password_hash(password_baru), username))
    conn.commit()
    return cur.rowcount > 0


def ganti_password(user_id: int, password_baru: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password_baru), user_id))
    conn.commit()


def ganti_username(user_id: int, username_baru: str) -> bool:
    """False bila username baru sudah dipakai pengguna lain (UNIQUE), True bila berhasil."""
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET username = ? WHERE id = ?", (username_baru, user_id))
        conn.commit()
        return True
    except Exception:
        return False


def cek_password_pengguna(user_id: int, password: str) -> bool:
    row = get_connection().execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None and check_password_hash(row["password_hash"], password)


def pastikan_akun_awal():
    """
    Membuat akun awal bila tabel users masih kosong. Nama dari ADMIN_USERNAME; kata sandi dari ADMIN_PASSWORD,
    atau dibuat ACAK bila tidak diatur.

    Returns:
        tuple | None: (username, password_acak_atau_None). None bila sudah ada pengguna.
    """
    if jumlah_pengguna() > 0:
        return None
    username = current_app.config["ADMIN_USERNAME"]
    dari_env = current_app.config["ADMIN_PASSWORD"]
    password = dari_env or "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    buat_pengguna(username, password, "Administrator")
    return username, (None if dari_env else password)
