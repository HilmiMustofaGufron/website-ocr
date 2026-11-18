"""
database/db.py
==============
Koneksi SQLite (sqlite3 murni, tanpa ORM: skala sistem ini satu server, satu berkas database).

Satu koneksi dipakai ulang sepanjang satu permintaan (disimpan di `g`) dan ditutup otomatis di akhir permintaan.
Untuk kode yang berjalan DI LUAR permintaan (mis. thread kamera) pakai `koneksi_mandiri()`.
"""

import os
import sqlite3
from contextlib import contextmanager

from flask import Flask, current_app, g

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Kolom yang ditambahkan SESUDAH versi pertama. Database lama (yang tabelnya sudah ada) tidak otomatis mendapat kolom baru
# dari CREATE TABLE IF NOT EXISTS, jadi ditambahkan di sini (aman diulang, data lama tidak disentuh).
KOLOM_TAMBAHAN = {
    "hasil_scan": [("teks_terbaca", "TEXT"), ("jarak_koreksi", "REAL")],
}


def _migrasi(conn: sqlite3.Connection) -> None:
    for tabel, kolom in KOLOM_TAMBAHAN.items():
        ada = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabel})")}
        for nama, tipe in kolom:
            if nama not in ada:
                conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {nama} {tipe}")


def _buka(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_connection() -> sqlite3.Connection:
    """Koneksi untuk permintaan yang sedang berjalan."""
    if "db_conn" not in g:
        g.db_conn = _buka(current_app.config["DATABASE_PATH"])
    return g.db_conn


def close_connection(exception=None) -> None:
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


@contextmanager
def koneksi_mandiri(path: str):
    """Koneksi sendiri (di luar permintaan Flask), otomatis ditutup."""
    conn = _buka(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(app: Flask) -> None:
    """Menjalankan schema.sql (aman diulang: semua pernyataan memakai IF NOT EXISTS / INSERT OR IGNORE)."""
    app.teardown_appcontext(close_connection)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        skema = f.read()
    with koneksi_mandiri(app.config["DATABASE_PATH"]) as conn:
        conn.executescript(skema)
        _migrasi(conn)
    app.logger.info("Database siap: %s", app.config["DATABASE_PATH"])
