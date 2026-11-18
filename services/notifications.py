"""
services/notifications.py
=========================
Notifikasi untuk operator (ikon lonceng di bilah atas). Tiga jenis:
  scan_tidak_dikenali : objek terdeteksi YOLO tetapi kodenya tidak dikenali atau tidak terbaca
  kamera_terputus     : koneksi kamera terputus saat membaca frame
  import_selesai      : import Excel master kode selesai
"""

from database.db import get_connection

TIPE_VALID = {"scan_tidak_dikenali", "kamera_terputus", "import_selesai"}
BATAS_TAMPIL = 20


def create(tipe: str, pesan: str) -> None:
    """Membuat satu notifikasi. Dipanggil di dalam application context (permintaan, atau `with app.app_context()`)."""
    if tipe not in TIPE_VALID:
        raise ValueError(f"Tipe notifikasi tidak dikenal: {tipe}")
    conn = get_connection()
    conn.execute("INSERT INTO notifikasi (tipe, pesan) VALUES (?, ?)", (tipe, str(pesan)[:300]))
    conn.commit()


def daftar_terbaru() -> dict:
    """Notifikasi terbaru (maksimal 20) dan jumlah yang belum dibaca, sesuai yang diharapkan notifications.js."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, tipe, pesan, dibaca, created_at FROM notifikasi ORDER BY id DESC LIMIT ?", (BATAS_TAMPIL,)
    ).fetchall()
    belum = conn.execute("SELECT COUNT(*) AS n FROM notifikasi WHERE dibaca = 0").fetchone()["n"]
    return {"notifikasi": [{**dict(r), "dibaca": bool(r["dibaca"])} for r in rows], "jumlah_belum_dibaca": belum}


def tandai_dibaca(notif_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("UPDATE notifikasi SET dibaca = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    return cur.rowcount > 0


def tandai_semua_dibaca() -> int:
    conn = get_connection()
    cur = conn.execute("UPDATE notifikasi SET dibaca = 1 WHERE dibaca = 0")
    conn.commit()
    return cur.rowcount
