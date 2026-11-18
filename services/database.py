"""
services/database.py
====================
Satu-satunya tempat query SQL. Blueprint memanggil fungsi di sini; tidak pernah menjalankan SQL langsung.
Semua fungsi mengembalikan dict biasa (bukan objek ORM), kecuali get_settings() yang mengembalikan objek
Pengaturan (bisa diakses sebagai pengaturan.threshold_yolo, juga di template).
"""

import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Optional

from database.db import get_connection

POLA_KODE = re.compile(r"^[A-Z0-9]{3,30}$")


class DataTidakValid(ValueError):
    """Masukan dari operator tidak memenuhi aturan (pesannya aman ditampilkan ke operator)."""


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def get_dashboard_summary() -> dict:
    """Ringkasan untuk Dashboard: scan hari ini, jumlah kode terdaftar, confidence dan waktu rata-rata hari ini."""
    conn = get_connection()
    hari_ini = date.today().isoformat()
    total_scan = conn.execute("SELECT COUNT(*) AS n FROM hasil_scan WHERE tanggal = ?", (hari_ini,)).fetchone()["n"]
    total_barang = conn.execute("SELECT COUNT(*) AS n FROM master_kode").fetchone()["n"]
    agregat = conn.execute(
        """
        SELECT AVG((confidence_yolo + confidence_ocr) / 2.0) AS conf_avg, AVG(processing_time) AS waktu_avg
        FROM hasil_scan WHERE tanggal = ?
        """,
        (hari_ini,),
    ).fetchone()
    return {
        "total_scan_hari_ini": total_scan,
        "total_barang": total_barang,
        "confidence_rata_rata": round(agregat["conf_avg"], 3) if agregat["conf_avg"] is not None else None,
        "processing_time_rata_rata": round(agregat["waktu_avg"], 3) if agregat["waktu_avg"] is not None else None,
    }


# ---------------------------------------------------------------------------
# Riwayat scan
# ---------------------------------------------------------------------------

_KOLOM_SCAN = (
    "id", "tanggal", "jam", "kode", "confidence_yolo", "confidence_ocr", "processing_time", "status",
    "waktu_yolo", "waktu_ocr", "waktu_recovery", "alasan_keputusan", "path_gambar", "path_crop", "path_deteksi",
    "teks_terbaca", "jarak_koreksi", "created_at",
)


def _scan_ke_dict(row) -> dict:
    return {k: row[k] for k in _KOLOM_SCAN}


def save_scan_result(hasil: dict) -> dict:
    """Menyimpan satu hasil scan (dict dari services.pipeline.scan_produk). Kode yang gagal dibaca tetap dicatat."""
    now = datetime.now()
    conn = get_connection()
    kode = hasil.get("kode")
    # Kode yang tidak ada di master_kode tidak boleh melanggar FK; simpan NULL (status tetap tercatat).
    if kode is not None and conn.execute("SELECT 1 FROM master_kode WHERE kode = ?", (kode,)).fetchone() is None:
        kode = None
    cur = conn.execute(
        """
        INSERT INTO hasil_scan
            (tanggal, jam, kode, confidence_yolo, confidence_ocr, processing_time, status,
             waktu_yolo, waktu_ocr, waktu_recovery, alasan_keputusan, path_gambar, path_crop, path_deteksi,
             teks_terbaca, jarak_koreksi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), kode,
            hasil.get("confidence_yolo") or 0.0, hasil.get("confidence_ocr") or 0.0,
            hasil.get("processing_time") or 0.0, hasil.get("status"),
            hasil.get("waktu_yolo"), hasil.get("waktu_ocr"), hasil.get("waktu_recovery"),
            hasil.get("alasan_keputusan"), hasil.get("path_gambar"), hasil.get("path_crop"), hasil.get("path_deteksi"),
            hasil.get("teks_terbaca"), hasil.get("jarak_koreksi"),
        ),
    )
    conn.commit()
    return _scan_ke_dict(conn.execute("SELECT * FROM hasil_scan WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_scan_history(limit: int = 50, offset: int = 0) -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM hasil_scan ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [_scan_ke_dict(r) for r in rows]


def search_scan_history(filters: dict, limit: int = 200) -> list:
    """Filter opsional: tanggal ('YYYY-MM-DD'), kode (sebagian cocok), status. Filter kosong diabaikan."""
    kondisi, param = [], []
    if filters.get("tanggal"):
        kondisi.append("tanggal = ?")
        param.append(filters["tanggal"])
    if filters.get("kode"):
        kondisi.append("kode LIKE ? ESCAPE '\\'")
        bersih = str(filters["kode"]).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        param.append(f"%{bersih}%")
    if filters.get("status"):
        kondisi.append("status = ?")
        param.append(filters["status"])

    query = "SELECT * FROM hasil_scan"
    if kondisi:
        query += " WHERE " + " AND ".join(kondisi)
    query += " ORDER BY id DESC LIMIT ?"
    param.append(limit)
    return [_scan_ke_dict(r) for r in get_connection().execute(query, param).fetchall()]


def get_scan_by_id(scan_id: int) -> Optional[dict]:
    row = get_connection().execute("SELECT * FROM hasil_scan WHERE id = ?", (scan_id,)).fetchone()
    return _scan_ke_dict(row) if row else None


def delete_scan_history(scan_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM hasil_scan WHERE id = ?", (scan_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Master kode
# ---------------------------------------------------------------------------

_cache_kode = None          # list[str] terurut abjad, atau None bila belum dimuat
_cache_lock = threading.Lock()


def invalidate_cache_kode() -> None:
    global _cache_kode
    with _cache_lock:
        _cache_kode = None


def get_daftar_kode_valid() -> list:
    """Daftar kode valid (list[str], urut abjad) untuk validasi hasil OCR. Di-cache; dibatalkan saat master kode berubah."""
    global _cache_kode
    with _cache_lock:
        if _cache_kode is None:
            rows = get_connection().execute("SELECT kode FROM master_kode ORDER BY kode ASC").fetchall()
            _cache_kode = [r["kode"] for r in rows]
        return list(_cache_kode)


def get_all_master_kode() -> list:
    rows = get_connection().execute("SELECT * FROM master_kode ORDER BY kode ASC").fetchall()
    return [dict(r) for r in rows]


def _bersihkan_kode(data: dict):
    kode = str(data.get("kode") or "").strip().upper()
    if not POLA_KODE.match(kode):
        raise DataTidakValid("Kode harus 3 sampai 30 karakter dan hanya berisi huruf A-Z atau angka 0-9 "
                             "(pembaca hanya mengenali karakter itu).")
    ket = data.get("keterangan")
    ket = None if ket is None or not str(ket).strip() else str(ket).strip()
    if ket and len(ket) > 200:
        raise DataTidakValid("Keterangan maksimal 200 karakter.")
    return kode, ket


def create_master_kode(data: dict) -> dict:
    kode, ket = _bersihkan_kode(data)
    conn = get_connection()
    try:
        cur = conn.execute("INSERT INTO master_kode (kode, keterangan) VALUES (?, ?)", (kode, ket))
        conn.commit()
    except sqlite3.IntegrityError:
        raise DataTidakValid(f"Kode '{kode}' sudah terdaftar.")
    invalidate_cache_kode()
    return dict(conn.execute("SELECT * FROM master_kode WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_master_kode(kode_id: int, data: dict) -> Optional[dict]:
    kode, ket = _bersihkan_kode(data)
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE master_kode SET kode = ?, keterangan = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (kode, ket, kode_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DataTidakValid(f"Kode '{kode}' sudah dipakai kode lain.")
    invalidate_cache_kode()
    if cur.rowcount == 0:
        return None
    return dict(conn.execute("SELECT * FROM master_kode WHERE id = ?", (kode_id,)).fetchone())


def delete_master_kode(kode_id: int) -> bool:
    """Menghapus kode. Riwayat scan lama TIDAK ikut terhapus (FK ON DELETE SET NULL)."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM master_kode WHERE id = ?", (kode_id,))
    conn.commit()
    invalidate_cache_kode()
    return cur.rowcount > 0


def import_master_kode_excel(file_stream) -> dict:
    """
    Import dari Excel (.xlsx). Kolom dicari tanpa membedakan huruf besar/kecil: 'kode' (wajib), 'keterangan'.
    Kode duplikat DILEWATI (tidak menimpa keterangan yang sudah ada).

    Returns:
        dict: berhasil, dilewati, gagal, detail_gagal
    """
    import pandas as pd

    df = pd.read_excel(file_stream)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "kode" not in df.columns:
        raise DataTidakValid("Kolom 'kode' tidak ditemukan di file Excel. Kolom yang ada: " + ", ".join(df.columns))

    ringkasan = {"berhasil": 0, "dilewati": 0, "gagal": 0, "detail_gagal": []}
    sudah_ada = {r["kode"] for r in get_all_master_kode()}
    for i, baris in df.iterrows():
        kode = str(baris.get("kode", "")).strip().upper()
        if not kode or kode == "NAN" or kode in sudah_ada:
            ringkasan["dilewati"] += 1
            continue
        ket = baris.get("keterangan")
        ket = None if ket is None or str(ket).strip().lower() == "nan" else str(ket).strip()
        try:
            create_master_kode({"kode": kode, "keterangan": ket})
            sudah_ada.add(kode)
            ringkasan["berhasil"] += 1
        except DataTidakValid as exc:
            ringkasan["gagal"] += 1
            ringkasan["detail_gagal"].append(f"Baris {i + 2}: {kode} -> {exc}")
    return ringkasan


# ---------------------------------------------------------------------------
# Pengaturan operator (tabel satu baris)
# ---------------------------------------------------------------------------

@dataclass
class Pengaturan:
    threshold_yolo: float = 0.4
    threshold_ocr: float = 0.6
    auto_scan: bool = True
    kamera_aktif: Optional[str] = None
    interval_scan: int = 500
    id: int = 1
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def get_settings() -> Pengaturan:
    row = get_connection().execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return Pengaturan(
        id=row["id"], threshold_yolo=row["threshold_yolo"], threshold_ocr=row["threshold_ocr"],
        auto_scan=bool(row["auto_scan"]), kamera_aktif=row["kamera_aktif"], interval_scan=row["interval_scan"],
        updated_at=row["updated_at"],
    )


def update_settings(data: dict) -> Pengaturan:
    """Pembaruan sebagian: field yang tidak dikirim tetap memakai nilai lama."""
    cur = get_settings()
    conn = get_connection()
    conn.execute(
        """
        UPDATE settings SET threshold_yolo = ?, threshold_ocr = ?, auto_scan = ?, kamera_aktif = ?,
                            interval_scan = ?, updated_at = datetime('now', 'localtime')
        WHERE id = 1
        """,
        (
            data.get("threshold_yolo", cur.threshold_yolo), data.get("threshold_ocr", cur.threshold_ocr),
            int(bool(data.get("auto_scan", cur.auto_scan))), data.get("kamera_aktif", cur.kamera_aktif),
            data.get("interval_scan", cur.interval_scan),
        ),
    )
    conn.commit()
    return get_settings()
