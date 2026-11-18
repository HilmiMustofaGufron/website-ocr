-- database/schema.sql
-- ====================
-- Skema database web baru. Tabel master_kode, hasil_scan, dan settings SAMA dengan versi sebelumnya
-- (kolom dan nama tidak berubah), jadi berkas warehouse.db lama dapat dipakai langsung bila ingin
-- memindahkan data. Ditambah dua tabel: users (login) dan notifikasi.
--
-- Catatan desain:
-- - master_kode.kode UNIQUE: satu kode hanya boleh terdaftar sekali.
-- - hasil_scan.kode boleh NULL: scan yang gagal tetap dicatat untuk audit dan evaluasi akurasi.
--   ON DELETE SET NULL: menghapus kode dari master tidak menghapus riwayat lama.
-- - settings: tabel satu baris (id selalu 1), di-seed otomatis.
-- - Kolom waktu_recovery dipertahankan demi kompatibilitas data lama; pada mode cepat nilainya selalu 0.

CREATE TABLE IF NOT EXISTS master_kode (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kode        TEXT NOT NULL UNIQUE,
    keterangan  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS hasil_scan (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal           TEXT NOT NULL,   -- 'YYYY-MM-DD'
    jam               TEXT NOT NULL,   -- 'HH:MM:SS'
    kode              TEXT,
    confidence_yolo   REAL NOT NULL,
    confidence_ocr    REAL NOT NULL,
    processing_time   REAL NOT NULL,   -- total, detik
    status            TEXT NOT NULL,   -- 'VALID' | 'INVALID' | 'NOT_FOUND'
    waktu_yolo        REAL,
    waktu_ocr         REAL,
    waktu_recovery    REAL,
    alasan_keputusan  TEXT,
    path_gambar       TEXT,
    path_crop         TEXT,
    path_deteksi      TEXT,
    teks_terbaca      TEXT,            -- bacaan OCR apa adanya (juga saat ditolak); NULL = tidak ada OCR / data lama
    jarak_koreksi     REAL,            -- jarak bacaan itu ke kode terdekat di Master Kode
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (kode) REFERENCES master_kode (kode)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    threshold_yolo  REAL NOT NULL DEFAULT 0.4,
    threshold_ocr   REAL NOT NULL DEFAULT 0.6,   -- tidak dipakai pada mode cepat; dipertahankan demi kompatibilitas data
    auto_scan       INTEGER NOT NULL DEFAULT 1,
    kamera_aktif    TEXT,
    interval_scan   INTEGER NOT NULL DEFAULT 500,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

INSERT OR IGNORE INTO settings (id, threshold_yolo, threshold_ocr, auto_scan, kamera_aktif, interval_scan)
VALUES (1, 0.4, 0.6, 1, NULL, 500);

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    nama_tampilan  TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS notifikasi (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipe        TEXT NOT NULL,        -- 'scan_tidak_dikenali' | 'kamera_terputus' | 'import_selesai'
    pesan       TEXT NOT NULL,
    dibaca      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_hasil_scan_tanggal ON hasil_scan (tanggal);
CREATE INDEX IF NOT EXISTS idx_hasil_scan_kode ON hasil_scan (kode);
CREATE INDEX IF NOT EXISTS idx_hasil_scan_status ON hasil_scan (status);
CREATE INDEX IF NOT EXISTS idx_notifikasi_dibaca ON notifikasi (dibaca);
